import json
import os
import sys
import time
from typing import Dict, List

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "ilustracaoes_de_sermoes")
SOURCE_JSONL = os.getenv("SOURCE_JSONL", "data/sermoncentral/sermoncentral_complete.jsonl")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "200"))
REQUEST_TIMEOUT_S = int(os.getenv("REQUEST_TIMEOUT_S", "120"))


def die(msg: str, code: int = 1):
    print(msg)
    sys.exit(code)


def load_rows(path: str) -> List[Dict]:
    if not os.path.exists(path):
        die(f"Arquivo nao encontrado: {path}")
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                die(f"JSON invalido em {path} linha {i}: {exc}")
    return rows


def iter_chunks(items: List[Dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main():
    if not SUPABASE_URL:
        die("Defina SUPABASE_URL.")
    if not SUPABASE_SERVICE_ROLE_KEY:
        die("Defina SUPABASE_SERVICE_ROLE_KEY.")
    if BATCH_SIZE <= 0:
        die("BATCH_SIZE deve ser > 0.")

    rows = [row for row in load_rows(SOURCE_JSONL) if row.get("uuid")]
    if not rows:
        die("Nenhum registro para enviar.", 0)

    endpoint = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    params = {"on_conflict": "uuid"}

    total = len(rows)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    sent = 0
    session = requests.Session()
    started = time.time()

    print(f"Migrando para {SUPABASE_TABLE}. Registros: {total}. Lotes: {total_batches}")
    for idx, batch in enumerate(iter_chunks(rows, BATCH_SIZE), start=1):
        payload = json.dumps(batch, ensure_ascii=False).encode("utf-8")
        resp = session.post(endpoint, params=params, headers=headers, data=payload, timeout=REQUEST_TIMEOUT_S, verify=False)
        if resp.status_code >= 300:
            preview = resp.text[:500]
            raise RuntimeError(f"Lote {idx}/{total_batches} falhou HTTP {resp.status_code}: {preview}")
        sent += len(batch)
        print(f"Lote {idx}/{total_batches} OK ({sent}/{total})")
        time.sleep(0.08)

    print(f"Concluido. enviados={sent}. tempo={time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
