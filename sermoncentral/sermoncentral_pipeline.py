import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR / "extrair") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "extrair"))

try:
    from content_taxonomy import classify_record
except Exception:
    def classify_record(record):  # fallback if taxonomy module is unavailable
        tags = []
        text = f"{record.get('title', '')} {record.get('summary', '')} {record.get('body_text', '')}".lower()
        if "faith" in text or "fe" in text:
            tags.append("tema:fe")
        if "love" in text or "amor" in text:
            tags.append("tema:amor")
        while len(tags) < 2:
            tags.append("tema:vida_crista")
        return sorted(set(tags))


BASE_URL = os.getenv("SERMONCENTRAL_BASE_URL", "https://www.sermoncentral.com").rstrip("/")
OUTPUT_PREFIX = os.getenv("SERMONCENTRAL_OUTPUT_PREFIX", "data/sermoncentral/sermoncentral_complete")
DB_PATH = os.getenv("SERMONCENTRAL_DB", "data/sermoncentral/sermoncentral_complete.sqlite")
MAX_LIST_PAGES = int(os.getenv("SERMONCENTRAL_MAX_LIST_PAGES", "120"))
MAX_DETAIL_ITEMS = int(os.getenv("SERMONCENTRAL_MAX_DETAIL_ITEMS", "0"))  # 0 = no limit
MAX_TOPICS = int(os.getenv("SERMONCENTRAL_MAX_TOPICS", "80"))  # 0 = no limit
REQUEST_TIMEOUT = int(os.getenv("SERMONCENTRAL_TIMEOUT", "45"))
SOURCES = [x.strip().lower() for x in os.getenv("SERMONCENTRAL_SOURCES", "illustrations,sermons,series,articles").split(",") if x.strip()]
REQUEST_DELAY = float(os.getenv("SERMONCENTRAL_DELAY", "0.5"))
SEARCH_KEYWORDS = [x.strip() for x in os.getenv("SERMONCENTRAL_KEYWORDS", "faith,hope,love,grace,prayer,church,leadership").split(",") if x.strip()]
REFRESH_EXISTING = os.getenv("SERMONCENTRAL_REFRESH_EXISTING", "false").strip().lower() in ("1", "true", "yes")


def slugify_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.replace("/", "-")[:240]


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value)
    fixes = {
        "\xa0": " ",
        "Ã¢â‚¬â„¢": "'",
        "Ã¢â‚¬Å“": '"',
        "Ã¢â‚¬Â": '"',
        "Ã¢â‚¬â€œ": "-",
        "Ã¢â‚¬â€": "-",
        "Ã‚ ": " ",
        "Ã‚": "",
    }
    for bad, good in fixes.items():
        text = text.replace(bad, good)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def parse_date_to_iso(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"\b([A-Za-z]+ \d{1,2}, \d{4})\b", text)
    if not match:
        return None
    try:
        dt = datetime.strptime(match.group(1), "%B %d, %Y")
        return dt.strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        return None


def stable_uuid(url: str) -> str:
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-a{digest[17:20]}-{digest[20:32]}"


def fetch_with_retry(session: requests.Session, url: str, params: Optional[dict] = None, retries: int = 5) -> Optional[requests.Response]:
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = min(2 ** (attempt - 1), 20)
                print(f"HTTP {resp.status_code} em {url}. retry em {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                return None
            return resp
        except requests.RequestException as exc:
            wait = min(2 ** (attempt - 1), 20)
            print(f"Erro de rede em {url} (tentativa {attempt}/{retries}): {exc}. retry em {wait}s")
            time.sleep(wait)
    return None


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
            "Referer": BASE_URL,
        }
    )
    email = os.getenv("SERMONCENTRAL_EMAIL", "").strip()
    password = os.getenv("SERMONCENTRAL_PASSWORD", "").strip()
    if not email or not password:
        print("Login nao configurado (SERMONCENTRAL_EMAIL/SERMONCENTRAL_PASSWORD). Coletando apenas conteudo publico.")
        return session

    login_url = f"{BASE_URL}/login"
    page = fetch_with_retry(session, login_url, retries=3)
    if not page:
        print("Falha ao abrir pagina de login. Continuando sem autenticacao.")
        return session
    soup = BeautifulSoup(page.content, "lxml")
    token = soup.find("input", {"name": "__RequestVerificationToken"})
    payload = {"email": email, "password": password}
    if token and token.get("value"):
        payload["__RequestVerificationToken"] = token["value"]

    try:
        resp = session.post(login_url, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code in (200, 302):
            print("Login solicitado. Sessao autenticada (ou parcialmente autenticada) iniciada.")
    except requests.RequestException as exc:
        print(f"Falha no login: {exc}. Continuando sem autenticacao.")
    return session


def init_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            uuid TEXT PRIMARY KEY,
            story_id INTEGER,
            slug TEXT,
            url TEXT UNIQUE,
            content_type TEXT,
            source_component TEXT,
            title TEXT,
            author TEXT,
            summary TEXT,
            body_text TEXT,
            citations TEXT,
            canonical_ref TEXT,
            categories TEXT,
            top_level_categories TEXT,
            bible_references TEXT,
            keywords TEXT,
            auto_tags TEXT,
            lang TEXT,
            published_at TEXT,
            updated_at TEXT,
            created_at TEXT,
            ai_text TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_type ON records(content_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_published_at ON records(published_at)")
    conn.commit()
    return conn


def extract_links(soup: BeautifulSoup, pattern: re.Pattern) -> List[str]:
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        full = urljoin(BASE_URL, href)
        if pattern.search(full):
            links.append(full)
    return sorted(set(links))


def get_illustration_topic_urls(session: requests.Session) -> List[str]:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    urls: Set[str] = set()
    for letter in letters:
        page = fetch_with_retry(
            session,
            f"{BASE_URL}/sermon-text-illustration-topics",
            params={"alpha": letter, "page": 1, "resourceTypeId": 2},
            retries=3,
        )
        if not page:
            continue
        soup = BeautifulSoup(page.content, "lxml")
        links = extract_links(soup, re.compile(r"/sermon-illustrations/sermon-illustrations-about-"))
        urls.update(links)
        print(f"[illustrations] letra {letter}: +{len(links)} topicos (acumulado {len(urls)})")
        if MAX_TOPICS > 0 and len(urls) >= MAX_TOPICS:
            break
        time.sleep(REQUEST_DELAY)
    all_urls = sorted(urls)
    if MAX_TOPICS > 0:
        return all_urls[:MAX_TOPICS]
    return all_urls


def collect_listing_urls(session: requests.Session, source: str) -> Set[str]:
    found: Set[str] = set()

    if source == "illustrations":
        topic_urls = get_illustration_topic_urls(session)
        print(f"[illustrations] topicos para varrer: {len(topic_urls)}")
        for idx, topic_url in enumerate(topic_urls, start=1):
            print(f"[illustrations] topico {idx}/{len(topic_urls)}")
            for page_num in range(1, MAX_LIST_PAGES + 1):
                page = fetch_with_retry(session, topic_url, params={"page": page_num}, retries=3)
                if not page:
                    break
                soup = BeautifulSoup(page.content, "lxml")
                links = extract_links(soup, re.compile(r"/sermon-illustrations/\d+/"))
                prev = len(found)
                found.update(links)
                print(f"[illustrations] topico {idx} pagina {page_num}: +{len(found)-prev} urls (acumulado {len(found)})")
                if len(links) == 0 or len(found) == prev:
                    break
                time.sleep(REQUEST_DELAY)
        return found

    seeds = {
        "sermons": [f"{BASE_URL}/sermons", f"{BASE_URL}/sermons/search?keyword=", f"{BASE_URL}/sermons/search?sortBy=Newest"],
        "series": [f"{BASE_URL}/sermon-series"],
        "articles": [
            f"{BASE_URL}/preachingarticles",
            f"{BASE_URL}/preachingarticles/search",
            f"{BASE_URL}/preachingarticles/search?sortBy=Newest",
        ],
    }
    patterns = {
        "sermons": re.compile(r"/sermons/(?!sermons-about-)[^/?#]+-\d+$"),
        "series": re.compile(r"/sermon-series/[^/?#]+$"),
        "articles": re.compile(r"/pastors-preaching-articles/[^/?#]+-\d+$"),
    }

    for seed in seeds.get(source, []):
        print(f"[{source}] seed: {seed}")
        for page_num in range(1, MAX_LIST_PAGES + 1):
            page = fetch_with_retry(session, seed, params={"page": page_num}, retries=3)
            if not page:
                break
            soup = BeautifulSoup(page.content, "lxml")
            links = extract_links(soup, patterns[source])
            prev = len(found)
            found.update(links)
            print(f"[{source}] pagina {page_num}: +{len(found)-prev} urls (acumulado {len(found)})")
            if len(links) == 0 or len(found) == prev:
                break
            time.sleep(REQUEST_DELAY)

    if source == "sermons":
        for kw in SEARCH_KEYWORDS:
            seed = f"{BASE_URL}/sermons/search?keyword={kw}"
            print(f"[sermons] seed keyword: {kw}")
            for page_num in range(1, MAX_LIST_PAGES + 1):
                page = fetch_with_retry(session, seed, params={"page": page_num}, retries=3)
                if not page:
                    break
                soup = BeautifulSoup(page.content, "lxml")
                links = extract_links(soup, patterns[source])
                prev = len(found)
                found.update(links)
                print(f"[sermons] kw={kw} pagina {page_num}: +{len(found)-prev} urls (acumulado {len(found)})")
                if len(links) == 0 or len(found) == prev:
                    break
                time.sleep(REQUEST_DELAY)
    return found


def soup_text(soup: BeautifulSoup) -> str:
    return normalize_text(soup.get_text(separator=" ", strip=True))


def pick_body(soup: BeautifulSoup) -> str:
    candidates = [
        "div.content",
        "article",
        ".article-list-item-body",
        ".article-body",
        ".entry-content",
        ".resource-body",
        "main",
    ]
    for selector in candidates:
        node = soup.select_one(selector)
        if not node:
            continue
        for trash in node.select("script,style,noscript,.ad-container,.resource-actions"):
            trash.decompose()
        text = normalize_text(node.get_text(separator="\n", strip=True))
        if len(text) > 60:
            return text
    return ""


def parse_record_from_url(session: requests.Session, url: str, source: str) -> Optional[Dict]:
    page = fetch_with_retry(session, url, retries=4)
    if not page:
        return None
    soup = BeautifulSoup(page.content, "lxml")
    page_text = soup_text(soup)

    title_node = soup.find("h1") or soup.select_one("h2")
    title = normalize_text(title_node.get_text(strip=True) if title_node else slugify_from_url(url))

    author_node = soup.find("a", href=lambda h: h and "/contributors/" in str(h))
    author = normalize_text(author_node.get_text(strip=True) if author_node else "")

    body_text = pick_body(soup)
    summary = normalize_text(body_text[:360]) if body_text else ""
    published_at = parse_date_to_iso(page_text)

    scripture_nodes = soup.select("a[href*='sermons/scripture'], a[href*='scripture']")
    scriptures = sorted({normalize_text(node.get_text(strip=True)) for node in scripture_nodes if node.get_text(strip=True)})

    cat_nodes = soup.select(
        "a[href*='sermon-illustrations-about'], a[href*='sermons-about'], a[href*='preachingarticles?topic'], a[href*='/sermon-series/']"
    )
    categories = sorted({normalize_text(node.get_text(strip=True)) for node in cat_nodes if node.get_text(strip=True)})

    kw = []
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        kw = [normalize_text(x) for x in meta_kw["content"].split(",") if normalize_text(x)]

    story_id = None
    if source == "illustrations":
        m = re.search(r"/sermon-illustrations/(\d+)/", url)
        story_id = int(m.group(1)) if m else None
    elif source == "sermons":
        m = re.search(r"-(\d+)$", urlparse(url).path)
        story_id = int(m.group(1)) if m else None

    content_type = {
        "illustrations": "sermoncentral_illustration",
        "sermons": "sermoncentral_sermon",
        "series": "sermoncentral_series",
        "articles": "sermoncentral_article",
    }.get(source, f"sermoncentral_{source}")

    row = {
        "uuid": stable_uuid(url),
        "story_id": story_id,
        "slug": slugify_from_url(url),
        "url": url,
        "content_type": content_type,
        "source_component": "sermoncentral",
        "title": title or "Sem titulo",
        "author": author or "Unknown",
        "summary": summary,
        "body_text": body_text,
        "citations": "",
        "canonical_ref": "",
        "categories": ", ".join(categories),
        "top_level_categories": source,
        "bible_references": ", ".join(scriptures),
        "keywords": ", ".join(kw),
        "auto_tags": "",
        "lang": "en",
        "published_at": published_at,
        "updated_at": utcnow_iso(),
        "created_at": published_at or utcnow_iso(),
        "ai_text": "",
    }
    ai_text = "\n\n".join(
        part
        for part in (
            f"Title: {row['title']}",
            f"Summary: {row['summary']}" if row["summary"] else "",
            f"Body: {row['body_text']}" if row["body_text"] else "",
            f"Categories: {row['categories']}" if row["categories"] else "",
            f"Scriptures: {row['bible_references']}" if row["bible_references"] else "",
        )
        if part
    )
    row["ai_text"] = ai_text
    row["auto_tags"] = ", ".join(classify_record(row))
    return row


def placeholder_record(url: str, source: str) -> Dict:
    content_type = {
        "illustrations": "sermoncentral_illustration",
        "sermons": "sermoncentral_sermon",
        "series": "sermoncentral_series",
        "articles": "sermoncentral_article",
    }.get(source, f"sermoncentral_{source}")
    slug = slugify_from_url(url)
    title = slug.replace("-", " ").strip().title()[:180] or "Sem titulo"
    row = {
        "uuid": stable_uuid(url),
        "story_id": None,
        "slug": slug,
        "url": url,
        "content_type": content_type,
        "source_component": "sermoncentral",
        "title": title,
        "author": "Unknown",
        "summary": "Detalhes indisponiveis nesta rodada.",
        "body_text": "",
        "citations": "",
        "canonical_ref": "",
        "categories": "",
        "top_level_categories": source,
        "bible_references": "",
        "keywords": "",
        "auto_tags": "tema:vida_crista, tema:reflexao",
        "lang": "en",
        "published_at": None,
        "updated_at": utcnow_iso(),
        "created_at": utcnow_iso(),
        "ai_text": f"Title: {title}\n\nSource URL: {url}\n\nNote: detail extraction unavailable.",
    }
    return row


def upsert_record(conn: sqlite3.Connection, row: Dict):
    cols = [
        "uuid",
        "story_id",
        "slug",
        "url",
        "content_type",
        "source_component",
        "title",
        "author",
        "summary",
        "body_text",
        "citations",
        "canonical_ref",
        "categories",
        "top_level_categories",
        "bible_references",
        "keywords",
        "auto_tags",
        "lang",
        "published_at",
        "updated_at",
        "created_at",
        "ai_text",
    ]
    placeholders = ", ".join([f":{c}" for c in cols])
    updates = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "uuid"])
    sql = f"""
    INSERT INTO records ({", ".join(cols)})
    VALUES ({placeholders})
    ON CONFLICT(uuid) DO UPDATE SET {updates}
    """
    conn.execute(sql, row)


def export_all(conn: sqlite3.Connection, output_prefix: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM records ORDER BY created_at DESC")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    dict_rows = [dict(zip(cols, row)) for row in rows]

    with open(f"{output_prefix}.json", "w", encoding="utf-8") as f:
        json.dump(dict_rows, f, ensure_ascii=False, indent=2)
    with open(f"{output_prefix}.jsonl", "w", encoding="utf-8") as f:
        for row in dict_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(f"{output_prefix}.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(dict_rows)


def run():
    conn = init_db(DB_PATH)
    session = create_session()
    total_new = 0
    total_skipped_existing = 0

    existing_urls: Set[str] = set()
    if not REFRESH_EXISTING:
        cur = conn.cursor()
        cur.execute("SELECT url FROM records WHERE url IS NOT NULL AND url != ''")
        existing_urls = {row[0] for row in cur.fetchall() if row and row[0]}
        print(f"Registros ja existentes no DB local: {len(existing_urls)}")

    for source in SOURCES:
        print(f"\n[{source}] coletando listagens...")
        urls = collect_listing_urls(session, source)
        if not urls:
            print(f"[{source}] nenhum URL encontrado.")
            continue

        print(f"[{source}] urls encontrados: {len(urls)}")
        processed = 0
        skipped_existing = 0
        source_new = 0
        for url in sorted(urls):
            if not REFRESH_EXISTING and url in existing_urls:
                skipped_existing += 1
                total_skipped_existing += 1
                continue
            row = parse_record_from_url(session, url, source)
            if not row:
                row = placeholder_record(url, source)
            upsert_record(conn, row)
            existing_urls.add(url)
            processed += 1
            source_new += 1
            total_new += 1
            if processed % 20 == 0:
                conn.commit()
                print(f"[{source}] {processed}/{len(urls)} detalhados")
            if MAX_DETAIL_ITEMS > 0 and processed >= MAX_DETAIL_ITEMS:
                print(f"[{source}] limite de detalhe atingido ({MAX_DETAIL_ITEMS})")
                break
            time.sleep(REQUEST_DELAY)
        conn.commit()
        print(f"[{source}] detalhados novos: {processed} | pulados_existentes: {skipped_existing} | novos_no_ciclo: {source_new}")

    print("\nExportando arquivos finais...")
    export_all(conn, OUTPUT_PREFIX)
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    print(
        f"Concluido. Registros totais no SQLite: {total}. Prefixo: {OUTPUT_PREFIX}. "
        f"Novos neste ciclo: {total_new}. Pulados existentes: {total_skipped_existing}."
    )
    conn.close()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    run()
