import json
import os
import sys
import time
from typing import Dict, Iterable, List


def _load_driver():
    try:
        import psycopg  # type: ignore

        return "psycopg", psycopg
    except Exception:
        pass

    try:
        import psycopg2  # type: ignore

        return "psycopg2", psycopg2
    except Exception:
        pass

    raise RuntimeError(
        "Instale um driver Postgres: `pip install psycopg[binary]` ou `pip install psycopg2-binary`."
    )


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SOURCE_JSONL = os.getenv("SOURCE_JSONL", "tpw_content_complete.jsonl")
TABLE_NAME = os.getenv("PG_TABLE", "public.ilustracaoes_de_sermoes")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))
SLEEP_BETWEEN_BATCHES_MS = int(os.getenv("SLEEP_BETWEEN_BATCHES_MS", "20"))

COLUMNS = [
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


def die(msg: str, code: int = 1):
    print(msg)
    sys.exit(code)


def parse_iso(value):
    if not value:
        return None
    text = str(value).strip()
    return text or None


def row_to_values(row: Dict) -> List:
    return [
        row.get("uuid"),
        row.get("story_id"),
        row.get("slug"),
        row.get("url"),
        row.get("content_type"),
        row.get("source_component"),
        row.get("title"),
        row.get("author"),
        row.get("summary"),
        row.get("body_text"),
        row.get("citations"),
        row.get("canonical_ref"),
        row.get("categories"),
        row.get("top_level_categories"),
        row.get("bible_references"),
        row.get("keywords"),
        row.get("auto_tags"),
        row.get("lang"),
        parse_iso(row.get("published_at")),
        parse_iso(row.get("updated_at")),
        parse_iso(row.get("created_at")),
        row.get("ai_text"),
    ]


def load_rows_stream(path: str) -> Iterable[Dict]:
    if not os.path.exists(path):
        die(f"Arquivo nao encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                die(f"JSON invalido em {path} linha {line_number}: {exc}")
            yield row


def iter_batches(rows: Iterable[Dict], size: int):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_upsert_sql():
    cols_sql = ", ".join(COLUMNS)
    placeholders = ", ".join(["%s"] * len(COLUMNS))
    updates = ", ".join([f"{c}=EXCLUDED.{c}" for c in COLUMNS if c != "uuid"])
    return (
        f"INSERT INTO {TABLE_NAME} ({cols_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT (uuid) DO UPDATE SET {updates}"
    )


def main():
    if not DATABASE_URL:
        die("Defina DATABASE_URL.")
    if BATCH_SIZE <= 0:
        die("BATCH_SIZE deve ser > 0.")

    driver_name, db = _load_driver()
    upsert_sql = build_upsert_sql()
    print(f"Driver: {driver_name}")
    print(f"Tabela destino: {TABLE_NAME}")
    print(f"Arquivo origem: {SOURCE_JSONL}")

    started = time.time()
    total_sent = 0
    batches_sent = 0

    if driver_name == "psycopg":
        conn = db.connect(DATABASE_URL)
    else:
        conn = db.connect(DATABASE_URL)

    try:
        with conn:
            with conn.cursor() as cur:
                for batch in iter_batches(load_rows_stream(SOURCE_JSONL), BATCH_SIZE):
                    values = [row_to_values(row) for row in batch if row.get("uuid")]
                    if not values:
                        continue
                    cur.executemany(upsert_sql, values)
                    total_sent += len(values)
                    batches_sent += 1
                    elapsed = time.time() - started
                    print(f"Lote {batches_sent} OK | enviados: {total_sent} | {elapsed:.1f}s")
                    if SLEEP_BETWEEN_BATCHES_MS > 0:
                        time.sleep(SLEEP_BETWEEN_BATCHES_MS / 1000.0)
    finally:
        conn.close()

    elapsed_total = time.time() - started
    print(f"Migracao direta concluida. Total upsert: {total_sent}. Tempo: {elapsed_total:.1f}s")


if __name__ == "__main__":
    main()
