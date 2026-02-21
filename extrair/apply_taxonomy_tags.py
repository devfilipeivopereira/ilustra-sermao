import csv
import json
import os
import sqlite3

from content_taxonomy import classify_record

OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "tpw_content_complete")


def load_records(output_prefix):
    path_jsonl = f"{output_prefix}.jsonl"
    path_json = f"{output_prefix}.json"

    if os.path.exists(path_jsonl):
        rows = []
        with open(path_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    if os.path.exists(path_json):
        with open(path_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data

    raise FileNotFoundError(
        f"Nao encontrei {path_jsonl} nem {path_json}. Rode a extracao antes de classificar."
    )


def save_json(records, output_prefix):
    with open(f"{output_prefix}.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def save_jsonl(records, output_prefix):
    with open(f"{output_prefix}.jsonl", "w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_csv(records, output_prefix):
    if not records:
        return
    fields = list(records[0].keys())
    with open(f"{output_prefix}.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def _has_column(cursor, table_name, column_name):
    rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def update_sqlite(records, output_prefix):
    db_path = f"{output_prefix}.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        if not _has_column(cur, "stories", "auto_tags"):
            cur.execute("ALTER TABLE stories ADD COLUMN auto_tags TEXT")

        cur.executemany(
            "UPDATE stories SET auto_tags = :auto_tags WHERE uuid = :uuid",
            records,
        )

        try:
            cur.execute("DROP TABLE IF EXISTS stories_fts")
            cur.execute(
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
            cur.executemany(
                """
                INSERT INTO stories_fts (
                    uuid, content_type, title, summary, body_text, ai_text, author, categories,
                    top_level_categories, bible_references, auto_tags
                )
                VALUES (
                    :uuid, :content_type, :title, :summary, :body_text, :ai_text, :author, :categories,
                    :top_level_categories, :bible_references, :auto_tags
                )
                """,
                records,
            )
        except sqlite3.OperationalError as exc:
            print(f"FTS5 nao disponivel neste SQLite. Detalhe: {exc}")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_stories_auto_tags ON stories(auto_tags)")
        conn.commit()
    finally:
        conn.close()


def main():
    records = load_records(OUTPUT_PREFIX)
    print(f"Registros carregados: {len(records)}")

    for row in records:
        tags = classify_record(row)
        row["auto_tags"] = ", ".join(tags)

    without_two = sum(1 for row in records if len([t for t in row["auto_tags"].split(",") if t.strip()]) < 2)
    print(f"Registros com menos de 2 tags: {without_two}")

    save_json(records, OUTPUT_PREFIX)
    save_jsonl(records, OUTPUT_PREFIX)
    save_csv(records, OUTPUT_PREFIX)
    update_sqlite(records, OUTPUT_PREFIX)
    print(f"Classificacao concluida e persistida em {OUTPUT_PREFIX}.(json/jsonl/csv/sqlite)")


if __name__ == "__main__":
    main()
