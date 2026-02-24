import argparse
import json
from pathlib import Path
from typing import Dict, List


TARGET = "View all articles by SermonCentral.com"


def replace_phrase(text: str, phrase: str) -> str:
    value = str(text or "")
    value = value.replace(phrase, "")
    value = value.replace(phrase.lower(), "")
    value = value.replace("View all articles by SermonCentral .com", "")
    return "\n".join(line.rstrip() for line in value.splitlines() if line.strip()).strip()


def clean_row(row: Dict, phrase: str, fields: List[str]) -> Dict:
    out = dict(row)
    for field in fields:
        if field in out and out[field] is not None:
            out[field] = replace_phrase(out[field], phrase)
    return out


def main():
    parser = argparse.ArgumentParser(description="Remove frase fixa de colunas textuais em JSONL.")
    parser.add_argument("--input", required=True, help="Arquivo JSONL de entrada.")
    parser.add_argument("--output", required=True, help="Arquivo JSONL de saida.")
    parser.add_argument("--phrase", default=TARGET, help="Frase a remover.")
    parser.add_argument(
        "--fields",
        default="body_text,summary,ai_text,citations",
        help="Colunas textuais CSV onde remover a frase.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Arquivo nao encontrado: {input_path}")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [item.strip() for item in args.fields.split(",") if item.strip()]
    total = 0
    changed = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
        for line in src:
            raw = line.strip()
            if not raw:
                continue
            total += 1
            row = json.loads(raw)
            cleaned = clean_row(row, args.phrase, fields)
            if cleaned != row:
                changed += 1
            dst.write(json.dumps(cleaned, ensure_ascii=False) + "\n")

    print(f"Total: {total}")
    print(f"Alterados: {changed}")
    print(f"Saida: {output_path}")


if __name__ == "__main__":
    main()
