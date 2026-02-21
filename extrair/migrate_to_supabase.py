import json
import os
import sys
import time
from typing import Dict, List

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE_NAME = os.getenv("SUPABASE_TABLE", "ilustracaoes_de_sermoes")
TABLE_FALLBACKS = os.getenv("SUPABASE_TABLE_FALLBACKS", "ilustracoes_de_sermoes")
SOURCE_JSONL = os.getenv("SOURCE_JSONL", "tpw_content_complete.jsonl")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
SLEEP_BETWEEN_BATCHES_MS = int(os.getenv("SLEEP_BETWEEN_BATCHES_MS", "80"))
REQUEST_TIMEOUT_S = int(os.getenv("REQUEST_TIMEOUT_S", "120"))
MAX_REQUEST_RETRIES = int(os.getenv("MAX_REQUEST_RETRIES", "6"))
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").strip().lower() not in ("0", "false", "no")


def die(msg: str, code: int = 1):
    print(msg)
    sys.exit(code)


def parse_iso(value):
    if not value:
        return None
    text = str(value).strip()
    return text or None


def row_to_payload(row: Dict) -> Dict:
    return {
        "uuid": row.get("uuid"),
        "story_id": row.get("story_id"),
        "slug": row.get("slug"),
        "url": row.get("url"),
        "content_type": row.get("content_type"),
        "source_component": row.get("source_component"),
        "title": row.get("title"),
        "author": row.get("author"),
        "summary": row.get("summary"),
        "body_text": row.get("body_text"),
        "citations": row.get("citations"),
        "canonical_ref": row.get("canonical_ref"),
        "categories": row.get("categories"),
        "top_level_categories": row.get("top_level_categories"),
        "bible_references": row.get("bible_references"),
        "keywords": row.get("keywords"),
        "auto_tags": row.get("auto_tags"),
        "lang": row.get("lang"),
        "published_at": parse_iso(row.get("published_at")),
        "updated_at": parse_iso(row.get("updated_at")),
        "created_at": parse_iso(row.get("created_at")),
        "ai_text": row.get("ai_text"),
    }


def load_rows(path: str) -> List[Dict]:
    if not os.path.exists(path):
        die(f"Arquivo nao encontrado: {path}")
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                die(f"JSON invalido em {path} linha {line_number}: {exc}")
    return rows


def chunks(items: List[Dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _auth_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Connection": "close",
    }


def resolve_table_name(session: requests.Session) -> str:
    candidates = [TABLE_NAME] + [item.strip() for item in TABLE_FALLBACKS.split(",") if item.strip()]
    tried = []
    for candidate in candidates:
        endpoint = f"{SUPABASE_URL}/rest/v1/{candidate}"
        tried.append(candidate)
        try:
            resp = session.get(
                endpoint,
                params={"select": "uuid", "limit": 1},
                headers=_auth_headers(),
                timeout=REQUEST_TIMEOUT_S,
                verify=VERIFY_SSL,
            )
        except requests.RequestException:
            continue

        if resp.status_code == 200:
            return candidate
        if resp.status_code in (401, 403):
            # A tabela existe, mas chave/politica bloqueou leitura.
            return candidate

    die(
        "Nao foi possivel resolver nome da tabela via REST. "
        f"Tentativas: {', '.join(tried)}. "
        "Verifique nome/schema da tabela e rode: NOTIFY pgrst, 'reload schema';"
    )


def upsert_batch(session: requests.Session, endpoint: str, payload_batch: List[Dict], batch_idx: int, total_batches: int):
    headers = _auth_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    params = {"on_conflict": "uuid"}

    body = json.dumps(payload_batch, ensure_ascii=False).encode("utf-8")

    for attempt in range(1, MAX_REQUEST_RETRIES + 1):
        try:
            resp = session.post(
                endpoint,
                params=params,
                headers=headers,
                data=body,
                timeout=REQUEST_TIMEOUT_S,
                verify=VERIFY_SSL,
            )

            if resp.status_code < 300:
                return

            # Retry em erros transitórios de infra
            if resp.status_code in (408, 425, 429, 500, 502, 503, 504):
                wait_s = min(2 ** (attempt - 1), 20)
                print(
                    f"Lote {batch_idx}/{total_batches} HTTP {resp.status_code} "
                    f"(tentativa {attempt}/{MAX_REQUEST_RETRIES}). Retry em {wait_s}s."
                )
                time.sleep(wait_s)
                continue

            preview = resp.text[:800]
            raise RuntimeError(
                f"Lote {batch_idx}/{total_batches} falhou HTTP {resp.status_code}. Resposta: {preview}"
            )
        except requests.RequestException as exc:
            if attempt == MAX_REQUEST_RETRIES:
                raise RuntimeError(
                    f"Lote {batch_idx}/{total_batches} falhou por erro de rede apos "
                    f"{MAX_REQUEST_RETRIES} tentativas: {exc}"
                ) from exc
            wait_s = min(2 ** (attempt - 1), 20)
            print(
                f"Lote {batch_idx}/{total_batches} erro de rede "
                f"(tentativa {attempt}/{MAX_REQUEST_RETRIES}): {exc}. Retry em {wait_s}s."
            )
            time.sleep(wait_s)


def main():
    if not SUPABASE_URL:
        die("Defina SUPABASE_URL.")
    if not SUPABASE_SERVICE_ROLE_KEY:
        die("Defina SUPABASE_SERVICE_ROLE_KEY.")
    if BATCH_SIZE <= 0:
        die("BATCH_SIZE deve ser > 0.")

    session = requests.Session()
    resolved_table = resolve_table_name(session)
    endpoint = f"{SUPABASE_URL}/rest/v1/{resolved_table}"
    rows = load_rows(SOURCE_JSONL)
    if not rows:
        die("Nenhum registro para migrar.", 0)

    payload = [row_to_payload(row) for row in rows if row.get("uuid")]
    total = len(payload)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Iniciando migracao para {resolved_table}. Registros: {total}. Lotes: {total_batches}.")
    started_at = time.time()
    sent = 0

    for idx, batch in enumerate(chunks(payload, BATCH_SIZE), start=1):
        upsert_batch(session, endpoint, batch, idx, total_batches)
        sent += len(batch)
        elapsed = time.time() - started_at
        print(f"Lote {idx}/{total_batches} OK | enviados: {sent}/{total} | {elapsed:.1f}s")
        if SLEEP_BETWEEN_BATCHES_MS > 0:
            time.sleep(SLEEP_BETWEEN_BATCHES_MS / 1000.0)

    elapsed_total = time.time() - started_at
    print(f"Migracao concluida. Total enviado: {sent}. Tempo: {elapsed_total:.1f}s.")


if __name__ == "__main__":
    main()
