import argparse
from collections import Counter
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Set

from bs4 import BeautifulSoup

import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
EXTRAIR_DIR = ROOT_DIR / "extrair"
if str(EXTRAIR_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRAIR_DIR))

try:
    from content_taxonomy import classify_record
except Exception:
    def classify_record(_record):
        return []

from llm_cleaner import LLMCleaner


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
SCRIPTURE_REF_RE = re.compile(
    r"\b(?:[1-3]\s*)?(?:genesis|exodus|leviticus|numbers|deuteronomy|joshua|judges|ruth|"
    r"samuel|kings|chronicles|ezra|nehemiah|esther|job|psalm|psalms|proverbs|ecclesiastes|"
    r"song of songs|isaiah|jeremiah|lamentations|ezekiel|daniel|hosea|joel|amos|obadiah|"
    r"jonah|micah|nahum|habakkuk|zephaniah|haggai|zechariah|malachi|matthew|mark|luke|john|"
    r"acts|romans|corinthians|galatians|ephesians|philippians|colossians|thessalonians|"
    r"timothy|titus|philemon|hebrews|james|peter|jude|revelation)\s+\d{1,3}:\d{1,3}"
    r"(?:-\d{1,3})?\b",
    re.IGNORECASE,
)
SCRIPTURE_REF_SIMPLE_RE = re.compile(r"^[1-3]?\s*[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]+\s+\d{1,3}:\d{1,3}(?:-\d{1,3})?$")
NOISE_LINE_PATTERNS = [
    re.compile(r"^View on one page$", re.IGNORECASE),
    re.compile(r"^Download Sermon (Slides|Graphics|\(Word Doc\))$", re.IGNORECASE),
    re.compile(r"^Download \(PDF\)$", re.IGNORECASE),
    re.compile(r"^Copy sermon$", re.IGNORECASE),
    re.compile(r"^Print$", re.IGNORECASE),
    re.compile(r"^Save$", re.IGNORECASE),
    re.compile(r"^View all Sermons$", re.IGNORECASE),
    re.compile(r"^Contributed by$", re.IGNORECASE),
    re.compile(r"^\(message contributor\)$", re.IGNORECASE),
    re.compile(r"^based on\s+\d+\s+ratings$", re.IGNORECASE),
    re.compile(r"^\(rate this sermon\)$", re.IGNORECASE),
    re.compile(r"^\|\s*[\d,]+\s+views$", re.IGNORECASE),
    re.compile(r"^(Scripture|Denomination|Summary):$", re.IGNORECASE),
]
THEME_BIBLE_FALLBACKS = {
    "tema:fe": ["Hebrews 11:1", "Romans 1:17", "Mark 9:23"],
    "tema:amor": ["1 Corinthians 13:4-7", "John 13:34", "1 John 4:8"],
    "tema:graca": ["Ephesians 2:8-9", "2 Corinthians 12:9", "Romans 5:8"],
    "tema:perdao": ["1 John 1:9", "Matthew 6:14-15", "Colossians 3:13"],
    "tema:oracao": ["Philippians 4:6-7", "1 Thessalonians 5:17", "Matthew 6:9"],
    "tema:esperanca": ["Romans 15:13", "Jeremiah 29:11", "Psalm 42:11"],
    "tema:ansiedade_medo": ["Psalm 23:4", "Isaiah 41:10", "1 Peter 5:7"],
    "tema:sofrimento": ["Romans 8:18", "Psalm 34:18", "2 Corinthians 1:3-4"],
    "tema:igreja_comunidade": ["Acts 2:42-47", "Hebrews 10:24-25", "1 Corinthians 12:27"],
    "tema:discipulado": ["Luke 9:23", "Matthew 28:19-20", "John 8:31"],
    "tema:humildade": ["Philippians 2:3-8", "James 4:6", "Micah 6:8"],
    "tema:vitoria_na_tentacao": ["1 Corinthians 10:13", "James 1:12", "Matthew 26:41"],
}
THEME_LABELS_PT = {
    "tema:fe": "fé",
    "tema:amor": "amor",
    "tema:duvida": "dúvida e confiança",
    "tema:esperanca": "esperança",
    "tema:graca": "graça",
    "tema:perdao": "perdão",
    "tema:oracao": "oração",
    "tema:adoracao": "adoração",
    "tema:sofrimento": "sofrimento e consolo",
    "tema:ansiedade_medo": "ansiedade e confiança em Deus",
    "tema:sabedoria": "sabedoria",
    "tema:discipulado": "discipulado",
    "tema:evangelismo_missao": "missão e evangelismo",
    "tema:igreja_comunidade": "igreja e comunhão",
    "tema:familia_relacionamentos": "família e relacionamentos",
    "tema:justica_compaixao": "justiça e compaixão",
    "tema:trabalho_dinheiro": "trabalho e mordomia",
    "tema:ressurreicao_vida_nova": "vida nova em Cristo",
    "tema:encarnacao_advento": "encarnação e advento",
    "tema:espirito_santo": "Espírito Santo",
    "tema:reino_de_deus": "Reino de Deus",
    "tema:arrependimento": "arrependimento",
    "tema:humildade": "humildade",
    "tema:vitoria_na_tentacao": "vitória na tentação",
    "tema:vida_crista": "vida cristã",
    "tema:reflexao": "reflexão cristã",
}
EXTRA_THEME_RULES = {
    "tema:humildade": ["humility", "humble", "humildade", "servo", "servir"],
    "tema:vitoria_na_tentacao": ["temptation", "tempted", "tentacao", "tentação", "resistir ao pecado"],
    "tema:vida_crista": ["christian life", "vida cristã", "santificação", "santificacao", "obediencia", "obediência"],
}


def fix_mojibake(value):
    if not value:
        return ""
    replacements = {
        "Ã¢â‚¬â„¢": "'",
        "Ã¢â‚¬Ëœ": "'",
        "Ã¢â‚¬Å“": '"',
        "Ã¢â‚¬Â": '"',
        "Ã¢â‚¬â€œ": "-",
        "Ã¢â‚¬â€": "-",
        "Ã¢â‚¬Â¦": "...",
        "Ã‚ ": " ",
        "Ã‚": "",
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


def clean_text(value: str, *, strip_html: bool = False, max_len: int = 0) -> str:
    text = str(value or "")
    text = fix_mojibake(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL_CHARS_RE.sub("", text)

    if strip_html and ("<" in text and ">" in text):
        text = BeautifulSoup(text, "html.parser").get_text("\n")
        text = HTML_TAG_RE.sub(" ", text)

    text = normalize_whitespace(text)
    if max_len > 0 and len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def parse_csv_set(value: str) -> set:
    return {item.strip().lower() for item in str(value or "").split(",") if item.strip()}


def slugify_tag(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def normalize_ref(value: str) -> str:
    text = normalize_whitespace(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    return text


def infer_theme_keys(row: Dict) -> List[str]:
    keys: List[str] = []
    seen: Set[str] = set()

    def push(key: str):
        clean = str(key or "").strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        keys.append(clean)

    for key in classify_record(row):
        push(key)

    full_text = " ".join(
        str(row.get(field, "") or "")
        for field in ("title", "summary", "body_text", "citations", "keywords", "categories", "top_level_categories")
    ).lower()
    folded = unicodedata.normalize("NFKD", full_text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    for key, terms in EXTRA_THEME_RULES.items():
        if any(term in full_text or term in folded for term in terms):
            push(key)

    while len(keys) < 3:
        for fallback in ("tema:vida_crista", "tema:fe", "tema:esperanca", "tema:amor", "tema:reflexao"):
            if fallback not in seen:
                push(fallback)
                break
        else:
            break
    return keys[:5]


def generate_content_tags(row: Dict) -> str:
    tags = [THEME_LABELS_PT.get(key, key.replace("tema:", "").replace("_", " ")) for key in infer_theme_keys(row)]
    return ", ".join(tags[:5])


def select_varied_tags(llm_tags: List[str], heuristic_tags: List[str], usage_counter: Counter, min_tags: int = 3, max_tags: int = 5) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()
    for raw in (llm_tags or []) + (heuristic_tags or []):
        tag = normalize_whitespace(str(raw or "")).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        candidates.append(tag)

    defaults = ["vida cristã", "fé", "esperança", "amor", "oração", "humildade", "disciplina espiritual"]
    for tag in defaults:
        if tag not in seen:
            candidates.append(tag)
            seen.add(tag)

    ranked = sorted(candidates, key=lambda t: (usage_counter[t], candidates.index(t)))
    selected = ranked[:max_tags]
    if len(selected) < min_tags:
        for tag in ranked[min_tags:]:
            if tag not in selected:
                selected.append(tag)
            if len(selected) >= min_tags:
                break
    return selected[:max_tags]


def generate_bible_text_refs(row: Dict, theme_keys: List[str], llm_refs: List[str] | None = None) -> str:
    refs: List[str] = []
    seen: Set[str] = set()

    def push_ref(value: str):
        ref = normalize_ref(value)
        if not ref:
            return
        if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", ref, re.IGNORECASE):
            return
        if not SCRIPTURE_REF_SIMPLE_RE.match(ref):
            return
        key = ref.lower()
        if key in seen:
            return
        seen.add(key)
        refs.append(ref)

    for field in ("bible_references", "canonical_ref"):
        for part in str(row.get(field, "") or "").split(","):
            push_ref(part)
    for ref in (llm_refs or []):
        push_ref(ref)

    haystack = "\n".join(
        str(row.get(field, "") or "")
        for field in ("title", "summary", "body_text", "citations")
    )
    for match in SCRIPTURE_REF_RE.findall(haystack):
        push_ref(match)

    for key in theme_keys:
        for ref in THEME_BIBLE_FALLBACKS.get(key, []):
            push_ref(ref)

    return ", ".join(refs[:7])


def strip_non_content_noise(text: str) -> str:
    lines = text.splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            filtered.append("")
            continue
        if any(pattern.match(stripped) for pattern in NOISE_LINE_PATTERNS):
            continue
        filtered.append(stripped)

    # Remove metadata-heavy header block before the first real paragraph.
    start_idx = 0
    for idx, line in enumerate(filtered):
        clean = line.strip()
        if len(clean) >= 90 and any(p in clean for p in (".", "?", "!", ";", ":")):
            start_idx = idx
            break
    content = "\n".join(filtered[start_idx:]) if filtered else ""
    return normalize_whitespace(content)


def iter_jsonl(paths: Iterable[Path]):
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"JSON invalido em {path} linha {line_no}: {exc}") from exc


def rebuild_ai_text(row: Dict) -> str:
    parts = [
        f"Type: {row.get('content_type', '')}".strip(),
        f"Title: {row.get('title', '')}".strip(),
        f"Summary: {row.get('summary', '')}".strip(),
        f"Body: {row.get('body_text', '')}".strip(),
        f"Citations: {row.get('citations', '')}".strip(),
        f"Canonical Ref: {row.get('canonical_ref', '')}".strip(),
    ]
    return "\n\n".join(part for part in parts if ":" in part and part.split(":", 1)[1].strip())


def clean_row(row: Dict, *, max_body_len: int, max_ai_len: int, recalc_tags: bool, strict_relevance: bool) -> Dict:
    out = dict(row)
    body = clean_text(out.get("body_text", ""), strip_html=True, max_len=0)
    if strict_relevance:
        body = strip_non_content_noise(body)
    out["body_text"] = clean_text(body, strip_html=False, max_len=max_body_len)
    out["summary"] = clean_text(out.get("summary", ""), strip_html=True)
    out["citations"] = clean_text(out.get("citations", ""), strip_html=False)
    out["ai_text"] = clean_text(rebuild_ai_text(out), strip_html=False, max_len=max_ai_len)
    if recalc_tags:
        out["auto_tags"] = ", ".join(classify_record(out))
    return out


def split_text_chunks(text: str, max_chars: int) -> Iterable[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        yield text
        return
    parts = text.split("\n\n")
    buf = []
    size = 0
    for part in parts:
        seg = part if not buf else "\n\n" + part
        if size + len(seg) <= max_chars:
            buf.append(part)
            size += len(seg)
            continue
        if buf:
            yield "\n\n".join(buf)
            buf = []
            size = 0
        if len(part) <= max_chars:
            buf = [part]
            size = len(part)
            continue
        start = 0
        while start < len(part):
            yield part[start : start + max_chars]
            start += max_chars
    if buf:
        yield "\n\n".join(buf)


def main():
    parser = argparse.ArgumentParser(description="Limpa conteudo textual de arquivos JSONL (foco: body_text).")
    parser.add_argument("--input", nargs="+", required=True, help="Um ou mais arquivos JSONL de entrada.")
    parser.add_argument("--output", required=True, help="Arquivo JSONL de saida.")
    parser.add_argument("--max-body-len", type=int, default=100000, help="Limite maximo de caracteres de body_text.")
    parser.add_argument("--max-ai-len", type=int, default=120000, help="Limite maximo de caracteres de ai_text.")
    parser.add_argument("--recalc-tags", action="store_true", help="Recalcula auto_tags com a taxonomia local.")
    parser.add_argument("--use-llm", action="store_true", help="Ativa verificacao LLM celula a celula para body_text.")
    parser.add_argument("--llm-provider", default="", help="openai | anthropic | ollama. Default via env LLM_PROVIDER.")
    parser.add_argument("--llm-model", default="", help="Modelo do provedor. Default via env LLM_MODEL.")
    parser.add_argument("--llm-limit", type=int, default=0, help="Limite de celulas body_text enviadas ao LLM (0 = sem limite).")
    parser.add_argument("--llm-min-chars", type=int, default=80, help="So envia ao LLM body_text com no minimo N caracteres.")
    parser.add_argument("--llm-timeout-s", type=int, default=90, help="Timeout por chamada LLM.")
    parser.add_argument("--llm-temperature", type=float, default=0.0, help="Temperatura do modelo.")
    parser.add_argument("--llm-min-ratio", type=float, default=0.55, help="Razao minima tamanho_saida/tamanho_entrada para aceitar resposta.")
    parser.add_argument("--llm-chunk-chars", type=int, default=6000, help="Maximo de caracteres por chamada LLM (0 = sem chunk).")
    parser.add_argument(
        "--llm-skip-types",
        default="sermon,series,sermoncentral_sermon,sermoncentral_series",
        help="Tipos de conteudo onde o LLM nao sera aplicado.",
    )
    parser.add_argument("--strict-relevance", action="store_true", help="Remove ruido de UI/metadata para manter apenas conteudo relevante.")
    parser.add_argument("--progress-every", type=int, default=100, help="Mostra progresso a cada N registros.")
    args = parser.parse_args()

    in_paths = [Path(p) for p in args.input]
    for p in in_paths:
        if not p.exists():
            raise SystemExit(f"Arquivo nao encontrado: {p}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    by_uuid: Dict[str, Dict] = {}
    total = 0
    changed = 0
    llm_calls = 0
    llm_changed = 0
    llm_rejected = 0
    llm_skipped_type = 0
    llm_metadata_calls = 0
    started = time.time()
    llm_skip_types = parse_csv_set(args.llm_skip_types)
    tag_usage: Counter = Counter()

    llm = None
    if args.use_llm:
        llm = LLMCleaner.from_env(
            provider=args.llm_provider,
            model=args.llm_model,
            timeout_s=args.llm_timeout_s,
            temperature=args.llm_temperature,
            min_ratio=args.llm_min_ratio,
        )
        print(f"LLM ativo: provider={llm.cfg.provider} model={llm.cfg.model}")

    for row in iter_jsonl(in_paths):
        total += 1
        uuid = str(row.get("uuid") or "").strip()
        if not uuid:
            continue
        cleaned = clean_row(
            row,
            max_body_len=args.max_body_len,
            max_ai_len=args.max_ai_len,
            recalc_tags=args.recalc_tags,
            strict_relevance=args.strict_relevance,
        )

        if llm is not None:
            body = str(cleaned.get("body_text", "") or "")
            ctype = str(cleaned.get("content_type", "") or "").strip().lower()
            can_send = len(body) >= args.llm_min_chars and (args.llm_limit <= 0 or llm_calls < args.llm_limit)
            if ctype in llm_skip_types:
                can_send = False
                llm_skipped_type += 1
            if can_send:
                out_chunks = []
                row_applied = False
                for chunk in split_text_chunks(body, args.llm_chunk_chars):
                    if args.llm_limit > 0 and llm_calls >= args.llm_limit:
                        out_chunks.append(chunk)
                        continue
                    llm_calls += 1
                    try:
                        llm_body, applied, reason = llm.clean_cell(chunk)
                        out_chunks.append(llm_body)
                        if applied:
                            row_applied = True
                        elif reason.startswith("ratio_guard") or reason.endswith("response"):
                            llm_rejected += 1
                    except Exception as exc:
                        llm_rejected += 1
                        out_chunks.append(chunk)
                        print(f"[LLM] uuid={uuid} erro={exc}")
                cleaned["body_text"] = clean_text("\n\n".join(out_chunks), strip_html=True, max_len=args.max_body_len)
                if row_applied:
                    llm_changed += 1
                try:
                    llm_metadata_calls += 1
                    meta = llm.enrich_cell(cleaned["body_text"][:18000])
                    candidate = clean_text(meta.get("cleaned_text", ""), strip_html=True, max_len=args.max_body_len)
                    if candidate:
                        if len(cleaned["body_text"]) < 400 or (len(candidate) / max(1, len(cleaned["body_text"])) >= args.llm_min_ratio):
                            cleaned["body_text"] = candidate
                    llm_tags = [str(t).strip().lower() for t in meta.get("content_tags", []) if str(t).strip()]
                    llm_refs = [str(r).strip() for r in meta.get("bible_text_refs", []) if str(r).strip()]
                except Exception as exc:
                    llm_tags = []
                    llm_refs = []
                    llm_rejected += 1
                    print(f"[LLM-META] uuid={uuid} erro={exc}")
            else:
                llm_tags = []
                llm_refs = []
            cleaned["ai_text"] = clean_text(rebuild_ai_text(cleaned), strip_html=False, max_len=args.max_ai_len)
            theme_keys = infer_theme_keys(cleaned)
            heuristic_tags = [THEME_LABELS_PT.get(key, key.replace("tema:", "").replace("_", " ")) for key in theme_keys]
            selected_tags = select_varied_tags(llm_tags, heuristic_tags, tag_usage, min_tags=3, max_tags=5)
            for tag in selected_tags:
                tag_usage[tag] += 1
            cleaned["content_tags"] = ", ".join(selected_tags)
            cleaned["bible_text_refs"] = generate_bible_text_refs(cleaned, theme_keys, llm_refs)
        else:
            theme_keys = infer_theme_keys(cleaned)
            heuristic_tags = [THEME_LABELS_PT.get(key, key.replace("tema:", "").replace("_", " ")) for key in theme_keys]
            selected_tags = select_varied_tags([], heuristic_tags, tag_usage, min_tags=3, max_tags=5)
            for tag in selected_tags:
                tag_usage[tag] += 1
            cleaned["content_tags"] = ", ".join(selected_tags)
            cleaned["bible_text_refs"] = generate_bible_text_refs(cleaned, theme_keys, [])

        if (
            str(row.get("body_text", "")) != str(cleaned.get("body_text", ""))
            or str(row.get("summary", "")) != str(cleaned.get("summary", ""))
            or str(row.get("citations", "")) != str(cleaned.get("citations", ""))
            or str(row.get("ai_text", "")) != str(cleaned.get("ai_text", ""))
            or str(row.get("content_tags", "")) != str(cleaned.get("content_tags", ""))
            or str(row.get("bible_text_refs", "")) != str(cleaned.get("bible_text_refs", ""))
            or (args.recalc_tags and str(row.get("auto_tags", "")) != str(cleaned.get("auto_tags", "")))
        ):
            changed += 1
        by_uuid[uuid] = cleaned
        if args.progress_every > 0 and total % args.progress_every == 0:
            elapsed = time.time() - started
            print(
                f"Progresso: {total} lidos | uuid={len(by_uuid)} | alterados={changed} "
                f"| llm_calls={llm_calls} | llm_changed={llm_changed} | {elapsed:.1f}s"
            )

    with out_path.open("w", encoding="utf-8") as f:
        for row in by_uuid.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Entrada total: {total}")
    print(f"UUID unicos: {len(by_uuid)}")
    print(f"Registros alterados: {changed}")
    if llm is not None:
        elapsed = time.time() - started
        print(f"LLM chamadas: {llm_calls}")
        print(f"LLM alterou body_text: {llm_changed}")
        print(f"LLM rejeicoes/erros: {llm_rejected}")
        print(f"LLM metadata calls: {llm_metadata_calls}")
        print(f"LLM pulados por tipo: {llm_skipped_type}")
        print(f"Tempo total: {elapsed:.1f}s")
    print(f"Saida: {out_path}")


if __name__ == "__main__":
    main()
