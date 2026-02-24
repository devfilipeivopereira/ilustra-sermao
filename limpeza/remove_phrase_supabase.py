import json
import os
import time
from typing import Dict, List

import requests


TARGETS = [
    "View all articles by SermonCentral.com",
    "View all articles by SermonCentral .com",
]
FIELDS = ["body_text", "summary", "ai_text", "citations"]


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE = os.getenv("SUPABASE_TABLE", "ilustracaoes_de_sermoes")
PAGE_SIZE = int(os.getenv("REMOVE_PHRASE_PAGE_SIZE", "1000"))
BATCH_SIZE = int(os.getenv("REMOVE_PHRASE_BATCH_SIZE", "200"))


def headers(extra: Dict | None = None):
    base = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        base.update(extra)
    return base


def clean_text(value: str) -> str:
    text = str(value or "")
    for target in TARGETS:
        text = text.replace(target, "")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line.strip()).strip()


def fetch_page(session: requests.Session, offset: int) -> List[Dict]:
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    params = {
        "select": "uuid,body_text,summary,ai_text,citations",
        "offset": str(offset),
        "limit": str(PAGE_SIZE),
        "order": "uuid.asc",
    }
    resp = session.get(url, params=params, headers=headers(), timeout=120)
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha fetch page {offset}: HTTP {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    return data if isinstance(data, list) else []


def build_updates(rows: List[Dict]) -> List[Dict]:
    updates = []
    for row in rows:
        uuid = row.get("uuid")
        if not uuid:
            continue
        changed = {"uuid": uuid}
        has_change = False
        for field in FIELDS:
            before = str(row.get(field) or "")
            after = clean_text(before)
            if before != after:
                changed[field] = after
                has_change = True
        if has_change:
            updates.append(changed)
    return updates


def chunks(items: List[Dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def upsert(session: requests.Session, batch: List[Dict]):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    params = {"on_conflict": "uuid"}
    resp = session.post(
        url,
        params=params,
        headers=headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
        timeout=120,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha upsert: HTTP {resp.status_code} {resp.text[:500]}")


def main():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise SystemExit("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente.")

    session = requests.Session()
    offset = 0
    total = 0
    total_changed = 0
    started = time.time()

    while True:
        rows = fetch_page(session, offset)
        if not rows:
            break
        total += len(rows)
        updates = build_updates(rows)
        total_changed += len(updates)
        for batch in chunks(updates, BATCH_SIZE):
            upsert(session, batch)
        offset += len(rows)
        print(f"Varridos: {total} | alterados: {total_changed}")

    elapsed = time.time() - started
    print(f"Concluido. Varridos={total} alterados={total_changed} tempo={elapsed:.1f}s")


if __name__ == "__main__":
    main()
