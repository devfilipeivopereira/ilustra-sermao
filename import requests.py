import csv
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

TOKEN = os.getenv("STORYBLOK_TOKEN", "3hIhvSE7QI09a294yaW73wtt")
BASE_URL = "https://api-us.storyblok.com/v2/cdn/stories"
PER_PAGE = int(os.getenv("PER_PAGE", "100"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
STARTS_WITH = os.getenv("STARTS_WITH", "sermon-illustrations/")
MAX_PAGES = int(os.getenv("MAX_PAGES", "0"))
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "illustrations_complete")


def fix_mojibake(value):
    if not value:
        return ""
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "-",
        "â€”": "-",
        "â€¦": "...",
        "Â ": " ",
        "Â": "",
    }
    text = str(value)
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def normalize_whitespace(value):
    if not value:
        return ""
    text = fix_mojibake(value)
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


def render_rich_text(node):
    if not node:
        return ""
    text = ""
    if isinstance(node, dict):
        if node.get("type") == "text":
            text += node.get("text", "")
        for key in ("content", "body"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    text += render_rich_text(child)
            elif isinstance(children, dict):
                text += render_rich_text(children)
        if node.get("type") in ("paragraph", "heading"):
            text += "\n\n"
    elif isinstance(node, list):
        for item in node:
            text += render_rich_text(item)
    return normalize_whitespace(text)


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return render_rich_text(value)
    return normalize_whitespace(value)


def list_to_csv_text(value):
    if not value:
        return ""
    if not isinstance(value, list):
        return as_text(value)
    parts = [as_text(item) for item in value]
    return ", ".join(part for part in parts if part)


def resolve_uuid(uuid_data, rel_map):
    if not uuid_data:
        return ""
    if isinstance(uuid_data, str):
        return rel_map.get(uuid_data, uuid_data)
    if isinstance(uuid_data, dict):
        return uuid_data.get("name", uuid_data.get("uuid", str(uuid_data)))
    return str(uuid_data)


def build_params(page):
    return {
        "version": "published",
        "per_page": PER_PAGE,
        "page": page,
        "token": TOKEN,
        "starts_with": STARTS_WITH,
        "is_startpage": 0,
        "resolve_relations": "illustration.author,illustration.illustration_categories,illustration.bible_references",
    }


def fetch_page(session, page, retries=5):
    params = build_params(page)
    for attempt in range(1, retries + 1):
        try:
            response = session.get(BASE_URL, params=params, timeout=45)
            status_code = response.status_code
            if status_code == 429 or 500 <= status_code < 600:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else min(2 ** (attempt - 1), 20)
                print(f"Pagina {page} retornou {status_code}. Aguardando {wait_seconds:.1f}s para retry.")
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            return json.loads(response.content.decode("utf-8")), page
        except requests.RequestException as exc:
            wait_seconds = min(2 ** (attempt - 1), 20)
            print(f"Erro na pagina {page} (tentativa {attempt}/{retries}): {exc}. Retry em {wait_seconds}s.")
            time.sleep(wait_seconds)
    return None, page


def process_data(all_data):
    rel_map = {}
    illustrations = []

    for data in all_data:
        if not data:
            continue
        for rel in data.get("rels", []):
            rel_map[rel["uuid"]] = rel["name"]

    for data in all_data:
        if not data:
            continue
        for story in data.get("stories", []):
            content = story.get("content", {})
            if content.get("component") != "illustration":
                continue

            body_text = as_text(content.get("content"))
            title = as_text(content.get("title")) or as_text(story.get("name"))
            summary = as_text(content.get("description"))
            citations = as_text(content.get("citations"))
            canonical_ref = as_text(content.get("canonical_ref"))

            categories = [resolve_uuid(item, rel_map) for item in content.get("illustration_categories", [])]
            bible_refs = [resolve_uuid(item, rel_map) for item in content.get("bible_references", [])]
            keywords = content.get("keywords", [])
            top_categories = content.get("top_level_categories", [])

            if not isinstance(keywords, list):
                keywords = [keywords]
            if not isinstance(top_categories, list):
                top_categories = [top_categories]

            ai_text = "\n\n".join(
                part
                for part in (
                    f"Title: {title}" if title else "",
                    f"Summary: {summary}" if summary else "",
                    f"Body: {body_text}" if body_text else "",
                    f"Citations: {citations}" if citations else "",
                    f"Canonical Ref: {canonical_ref}" if canonical_ref else "",
                )
                if part
            )

            illustrations.append(
                {
                    "uuid": story.get("uuid"),
                    "story_id": story.get("id"),
                    "slug": story.get("full_slug"),
                    "url": f"https://thepastorsworkshop.com/{story.get('full_slug')}",
                    "title": title,
                    "author": resolve_uuid(content.get("author"), rel_map) or "Unknown",
                    "summary": summary,
                    "body_text": body_text,
                    "citations": citations,
                    "canonical_ref": canonical_ref,
                    "categories": list_to_csv_text(categories),
                    "bible_references": list_to_csv_text(bible_refs),
                    "keywords": list_to_csv_text(keywords),
                    "top_level_categories": list_to_csv_text(top_categories),
                    "lang": story.get("lang"),
                    "published_at": story.get("published_at"),
                    "updated_at": story.get("updated_at"),
                    "created_at": story.get("created_at"),
                    "ai_text": ai_text,
                }
            )

    return illustrations


def write_json(records, output_prefix):
    with open(f"{output_prefix}.json", "w", encoding="utf-8") as json_file:
        json.dump(records, json_file, ensure_ascii=False, indent=2)


def write_jsonl(records, output_prefix):
    with open(f"{output_prefix}.jsonl", "w", encoding="utf-8") as jsonl_file:
        for row in records:
            jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(records, output_prefix):
    if not records:
        return
    fields = list(records[0].keys())
    with open(f"{output_prefix}.csv", "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def write_sqlite(records, output_prefix):
    db_path = f"{output_prefix}.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS stories")
        cursor.execute(
            """
            CREATE TABLE stories (
                uuid TEXT PRIMARY KEY,
                story_id INTEGER,
                slug TEXT,
                url TEXT,
                title TEXT,
                author TEXT,
                summary TEXT,
                body_text TEXT,
                citations TEXT,
                canonical_ref TEXT,
                categories TEXT,
                bible_references TEXT,
                keywords TEXT,
                top_level_categories TEXT,
                lang TEXT,
                published_at TEXT,
                updated_at TEXT,
                created_at TEXT,
                ai_text TEXT
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_slug ON stories(slug)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_author ON stories(author)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_published_at ON stories(published_at)")

        cursor.executemany(
            """
            INSERT INTO stories (
                uuid, story_id, slug, url, title, author, summary, body_text, citations, canonical_ref,
                categories, bible_references, keywords, top_level_categories, lang, published_at,
                updated_at, created_at, ai_text
            )
            VALUES (
                :uuid, :story_id, :slug, :url, :title, :author, :summary, :body_text, :citations, :canonical_ref,
                :categories, :bible_references, :keywords, :top_level_categories, :lang, :published_at,
                :updated_at, :created_at, :ai_text
            )
            """,
            records,
        )

        try:
            cursor.execute("DROP TABLE IF EXISTS stories_fts")
            cursor.execute(
                """
                CREATE VIRTUAL TABLE stories_fts USING fts5(
                    uuid UNINDEXED,
                    title,
                    summary,
                    body_text,
                    ai_text,
                    author,
                    categories,
                    bible_references
                )
                """
            )
            cursor.executemany(
                """
                INSERT INTO stories_fts (
                    uuid, title, summary, body_text, ai_text, author, categories, bible_references
                )
                VALUES (
                    :uuid, :title, :summary, :body_text, :ai_text, :author, :categories, :bible_references
                )
                """,
                records,
            )
        except sqlite3.OperationalError as exc:
            print(f"FTS5 nao disponivel neste SQLite. Busca full-text foi ignorada. Detalhe: {exc}")

        conn.commit()
    finally:
        conn.close()


def fetch_all_pages():
    session = requests.Session()
    print("Obtendo total de paginas...")
    initial_data, _ = fetch_page(session, 1)
    if not initial_data:
        raise RuntimeError("Nao foi possivel carregar a pagina 1.")

    total_raw = initial_data.get("total")
    if total_raw:
        total_items = int(total_raw)
        total_pages = (total_items // PER_PAGE) + (1 if total_items % PER_PAGE > 0 else 0)
        if MAX_PAGES > 0:
            total_pages = min(total_pages, MAX_PAGES)
        print(f"Total de itens: {total_items}, Total de paginas: {total_pages}")

        all_raw_data = [None] * (total_pages + 1)
        all_raw_data[1] = initial_data
        pages_to_fetch = list(range(2, total_pages + 1))

        failed_pages = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_page = {executor.submit(fetch_page, session, page): page for page in pages_to_fetch}
            for future in as_completed(future_to_page):
                data, page = future.result()
                if data is None:
                    failed_pages.append(page)
                else:
                    all_raw_data[page] = data
                print(f"Pagina {page} concluida.")

        if failed_pages:
            print(f"Reprocessando paginas com falha: {failed_pages}")
        for page in failed_pages:
            data, _ = fetch_page(session, page, retries=5)
            all_raw_data[page] = data

        still_failed = [page for page in range(1, total_pages + 1) if all_raw_data[page] is None]
        if still_failed:
            raise RuntimeError(f"Falha definitiva nas paginas: {still_failed}")
        return all_raw_data

    print("Campo 'total' nao veio na API. Usando paginacao incremental ate pagina vazia.")
    all_raw_data = [None, initial_data]
    page = 2
    max_page_limit = MAX_PAGES if MAX_PAGES > 0 else 1000000
    while page <= max_page_limit:
        data, _ = fetch_page(session, page, retries=5)
        if data is None:
            raise RuntimeError(f"Falha definitiva na pagina {page} sem total conhecido.")
        stories = data.get("stories", [])
        if not stories:
            break
        all_raw_data.append(data)
        print(f"Pagina {page} concluida.")
        page += 1

    print(f"Paginas coletadas: {len(all_raw_data) - 1}")
    return all_raw_data


def main():
    if not TOKEN:
        raise RuntimeError("Defina STORYBLOK_TOKEN no ambiente.")

    all_raw_data = fetch_all_pages()
    print("Processando dados...")
    records = process_data(all_raw_data)

    print(f"Salvando {len(records)} registros...")
    write_json(records, OUTPUT_PREFIX)
    write_jsonl(records, OUTPUT_PREFIX)
    write_csv(records, OUTPUT_PREFIX)
    write_sqlite(records, OUTPUT_PREFIX)
    print(f"Extracao finalizada. Arquivos gerados com prefixo '{OUTPUT_PREFIX}'.")


if __name__ == "__main__":
    main()
