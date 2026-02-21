import csv
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from content_taxonomy import classify_record

TOKEN = os.getenv("STORYBLOK_TOKEN", "3hIhvSE7QI09a294yaW73wtt")
BASE_URL = "https://api-us.storyblok.com/v2/cdn/stories"
PER_PAGE = int(os.getenv("PER_PAGE", "100"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "0"))
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "tpw_content_complete")
FOLDERS = os.getenv(
    "FOLDERS",
    "sermon-illustrations,quotes,liturgy,series",
).split(",")


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
        node_type = node.get("type")
        if node_type == "text":
            text += node.get("text", "")
        if node_type == "hard_break":
            text += "\n"

        for key in ("content", "body"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    text += render_rich_text(child)
            elif isinstance(children, dict):
                text += render_rich_text(children)

        if node_type in ("paragraph", "heading"):
            text += "\n\n"

    elif isinstance(node, list):
        for item in node:
            text += render_rich_text(item)

    return normalize_whitespace(text)


def deep_collect_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return normalize_whitespace(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(part for part in (deep_collect_text(item) for item in value) if part).strip()
    if isinstance(value, dict):
        doc_text = render_rich_text(value)
        if doc_text:
            return doc_text

        priority_keys = (
            "title",
            "name",
            "description",
            "summary",
            "subtitle",
            "text",
            "content",
            "body",
        )
        parts = []
        for key in priority_keys:
            if key in value:
                part = deep_collect_text(value.get(key))
                if part:
                    parts.append(part)

        for key, item in value.items():
            if key in priority_keys:
                continue
            part = deep_collect_text(item)
            if part:
                parts.append(part)

        return normalize_whitespace("\n".join(parts))

    return normalize_whitespace(str(value))


def as_text(value):
    return deep_collect_text(value)


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
        uuid = uuid_data.get("uuid")
        if uuid and uuid in rel_map:
            return rel_map[uuid]
        return uuid_data.get("name", uuid_data.get("uuid", str(uuid_data)))
    return str(uuid_data)


def parse_bible_reference(item, rel_map):
    if not item:
        return ""
    if isinstance(item, str):
        return resolve_uuid(item, rel_map)
    if not isinstance(item, dict):
        return as_text(item)

    if item.get("component") == "bible_reference":
        book_name = resolve_uuid(item.get("book"), rel_map)
        chapter = as_text(item.get("chapter"))
        verse = as_text(item.get("verse"))
        if book_name and chapter and verse:
            return f"{book_name} {chapter}:{verse}"
        if book_name and chapter:
            return f"{book_name} {chapter}"

    return as_text(item)


def parse_citations(value):
    if not value:
        return ""
    if isinstance(value, list):
        chunks = []
        for item in value:
            text = ""
            if isinstance(item, dict):
                text = as_text(item.get("published_work")) or as_text(item.get("copyright")) or as_text(item)
            else:
                text = as_text(item)
            if text:
                chunks.append(text)
        return " | ".join(chunks)
    return as_text(value)


def build_params(folder, page):
    return {
        "version": "published",
        "per_page": PER_PAGE,
        "page": page,
        "token": TOKEN,
        "starts_with": f"{folder.strip()}/",
        "is_startpage": 0,
        "resolve_relations": (
            "illustration.author,illustration.illustration_categories,illustration.bible_references,"
            "quote.author,quote.keywords,quote.top_level_categories,quote.bible_references,"
            "liturgy.author,liturgy.keywords,liturgy.top_level_categories,liturgy.bible_references,"
            "liturgy.liturgy_categories"
        ),
    }


def fetch_page(session, folder, page, retries=5):
    params = build_params(folder, page)
    for attempt in range(1, retries + 1):
        try:
            response = session.get(BASE_URL, params=params, timeout=45)
            status_code = response.status_code
            if status_code == 429 or 500 <= status_code < 600:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else min(2 ** (attempt - 1), 20)
                print(f"[{folder}] Pagina {page} retornou {status_code}. Retry em {wait_seconds:.1f}s.")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            total_header = response.headers.get("total")
            total_items = int(total_header) if total_header and str(total_header).isdigit() else None
            return response.json(), page, total_items
        except requests.RequestException as exc:
            wait_seconds = min(2 ** (attempt - 1), 20)
            print(f"[{folder}] Erro na pagina {page} ({attempt}/{retries}): {exc}. Retry em {wait_seconds}s.")
            time.sleep(wait_seconds)
    return None, page, None


def fetch_folder_data(session, folder):
    print(f"\n[{folder}] Obtendo total de paginas...")
    initial_data, _, header_total = fetch_page(session, folder, 1)
    if not initial_data:
        raise RuntimeError(f"[{folder}] Nao foi possivel carregar a pagina 1.")

    total_raw = initial_data.get("total")
    total_items = None
    if total_raw and str(total_raw).isdigit():
        total_items = int(total_raw)
    elif header_total is not None:
        total_items = header_total

    if total_items is None:
        print(f"[{folder}] Total nao informado. Usando paginacao incremental.")
        all_raw_data = [None, initial_data]
        page = 2
        max_page_limit = MAX_PAGES if MAX_PAGES > 0 else 1000000
        while page <= max_page_limit:
            data, _, _ = fetch_page(session, folder, page, retries=5)
            if data is None:
                raise RuntimeError(f"[{folder}] Falha definitiva na pagina {page} sem total conhecido.")
            stories = data.get("stories", [])
            if not stories:
                break
            all_raw_data.append(data)
            print(f"[{folder}] Pagina {page} concluida.")
            page += 1
        print(f"[{folder}] Paginas coletadas: {len(all_raw_data) - 1}")
        return all_raw_data

    total_pages = (total_items // PER_PAGE) + (1 if total_items % PER_PAGE > 0 else 0)
    total_pages = max(total_pages, 1)
    if MAX_PAGES > 0:
        total_pages = min(total_pages, MAX_PAGES)
    print(f"[{folder}] Total de itens: {total_items}, total de paginas: {total_pages}")

    all_raw_data = [None] * (total_pages + 1)
    all_raw_data[1] = initial_data
    pages_to_fetch = list(range(2, total_pages + 1))

    failed_pages = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_page = {
            executor.submit(fetch_page, session, folder, page): page
            for page in pages_to_fetch
        }
        for future in as_completed(future_to_page):
            data, page, _ = future.result()
            if data is None:
                failed_pages.append(page)
            else:
                all_raw_data[page] = data
            print(f"[{folder}] Pagina {page} concluida.")

    if failed_pages:
        print(f"[{folder}] Reprocessando paginas com falha: {failed_pages}")
    for page in failed_pages:
        data, _, _ = fetch_page(session, folder, page, retries=5)
        all_raw_data[page] = data

    still_failed = [page for page in range(1, total_pages + 1) if all_raw_data[page] is None]
    if still_failed:
        raise RuntimeError(f"[{folder}] Falha definitiva nas paginas: {still_failed}")

    return all_raw_data


def process_story(story, rel_map):
    content = story.get("content", {}) or {}
    component = content.get("component")
    slug = story.get("full_slug", "")

    content_type = component or "unknown"
    if slug.startswith("sermon-illustrations/"):
        content_type = "illustration"
    elif slug.startswith("quotes/"):
        content_type = "quote"
    elif slug.startswith("liturgy/"):
        content_type = "liturgy"
    elif slug.startswith("series/"):
        content_type = "series"

    title = as_text(content.get("title")) or as_text(story.get("name"))
    summary = as_text(content.get("description"))
    body_text = as_text(content.get("content")) or as_text(content.get("body"))
    citations = parse_citations(content.get("citations"))
    canonical_ref = as_text(content.get("canonical_ref"))

    primary_categories = []
    if content_type == "illustration":
        primary_categories = [resolve_uuid(item, rel_map) for item in content.get("illustration_categories", [])]
    if content_type == "liturgy":
        primary_categories = [resolve_uuid(item, rel_map) for item in content.get("liturgy_categories", [])]

    top_categories = [resolve_uuid(item, rel_map) for item in content.get("top_level_categories", [])]
    keywords = [resolve_uuid(item, rel_map) for item in content.get("keywords", [])]
    bible_refs = [parse_bible_reference(item, rel_map) for item in content.get("bible_references", [])]

    ai_text = "\n\n".join(
        part
        for part in (
            f"Type: {content_type}" if content_type else "",
            f"Title: {title}" if title else "",
            f"Summary: {summary}" if summary else "",
            f"Body: {body_text}" if body_text else "",
            f"Citations: {citations}" if citations else "",
            f"Canonical Ref: {canonical_ref}" if canonical_ref else "",
        )
        if part
    )

    row = {
        "uuid": story.get("uuid"),
        "story_id": story.get("id"),
        "slug": slug,
        "url": f"https://thepastorsworkshop.com/{slug}" if slug else "",
        "content_type": content_type,
        "source_component": component,
        "title": title,
        "author": resolve_uuid(content.get("author"), rel_map) or "Unknown",
        "summary": summary,
        "body_text": body_text,
        "citations": citations,
        "canonical_ref": canonical_ref,
        "categories": list_to_csv_text(primary_categories),
        "top_level_categories": list_to_csv_text(top_categories),
        "bible_references": list_to_csv_text(bible_refs),
        "keywords": list_to_csv_text(keywords),
        "lang": story.get("lang"),
        "published_at": story.get("published_at"),
        "updated_at": story.get("updated_at"),
        "created_at": story.get("created_at"),
        "ai_text": ai_text,
    }
    row["auto_tags"] = ", ".join(classify_record(row))
    return row


def process_data(all_data):
    rel_map = {}
    rows = []

    for data in all_data:
        if not data:
            continue
        for rel in data.get("rels", []):
            if rel.get("uuid") and rel.get("name"):
                rel_map[rel["uuid"]] = rel["name"]

    for data in all_data:
        if not data:
            continue
        for story in data.get("stories", []):
            rows.append(process_story(story, rel_map))

    return rows


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
                lang TEXT,
                published_at TEXT,
                updated_at TEXT,
                created_at TEXT,
                ai_text TEXT,
                auto_tags TEXT
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_slug ON stories(slug)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_type ON stories(content_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_author ON stories(author)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_published_at ON stories(published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_auto_tags ON stories(auto_tags)")

        cursor.executemany(
            """
            INSERT INTO stories (
                uuid, story_id, slug, url, content_type, source_component, title, author, summary, body_text,
                citations, canonical_ref, categories, top_level_categories, bible_references, keywords,
                lang, published_at, updated_at, created_at, ai_text, auto_tags
            )
            VALUES (
                :uuid, :story_id, :slug, :url, :content_type, :source_component, :title, :author, :summary, :body_text,
                :citations, :canonical_ref, :categories, :top_level_categories, :bible_references, :keywords,
                :lang, :published_at, :updated_at, :created_at, :ai_text, :auto_tags
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
                    content_type,
                    title,
                    summary,
                    body_text,
                    ai_text,
                    author,
                    categories,
                    top_level_categories,
                    bible_references,
                    auto_tags
                )
                """
            )
            cursor.executemany(
                """
                INSERT INTO stories_fts (
                    uuid, content_type, title, summary, body_text, ai_text, author, categories, top_level_categories, bible_references, auto_tags
                )
                VALUES (
                    :uuid, :content_type, :title, :summary, :body_text, :ai_text, :author, :categories, :top_level_categories, :bible_references, :auto_tags
                )
                """,
                records,
            )
        except sqlite3.OperationalError as exc:
            print(f"FTS5 nao disponivel neste SQLite. Busca full-text ignorada. Detalhe: {exc}")

        conn.commit()
    finally:
        conn.close()


def main():
    if not TOKEN:
        raise RuntimeError("Defina STORYBLOK_TOKEN no ambiente.")

    session = requests.Session()
    all_pages = []
    for folder in [item.strip() for item in FOLDERS if item.strip()]:
        folder_data = fetch_folder_data(session, folder)
        all_pages.extend(folder_data[1:])

    print("\nProcessando dados...")
    records = process_data(all_pages)
    print(f"Registros processados: {len(records)}")

    print("Salvando arquivos...")
    write_json(records, OUTPUT_PREFIX)
    write_jsonl(records, OUTPUT_PREFIX)
    write_csv(records, OUTPUT_PREFIX)
    write_sqlite(records, OUTPUT_PREFIX)
    print(f"Pipeline finalizado. Prefixo de saida: '{OUTPUT_PREFIX}'.")


if __name__ == "__main__":
    main()
