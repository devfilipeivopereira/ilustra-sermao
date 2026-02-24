import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests


SYSTEM_PROMPT = (
    "Voce e um limpador de texto. Sua tarefa e preservar o conteudo integral, "
    "apenas removendo lixo tecnico (markup residual, artefatos de encoding, "
    "ruido nao textual). Nunca resuma, nunca parafraseie, nunca omita ideias."
)


USER_PROMPT_TEMPLATE = """Limpe o texto abaixo mantendo 100% do conteudo semantico.
Regras obrigatorias:
1) Nao resumir.
2) Nao reescrever estilo.
3) Nao traduzir.
4) Nao adicionar comentarios.
5) Retornar somente o texto final limpo.

Texto:
---
{text}
---
"""
METADATA_PROMPT_TEMPLATE = """Analise o conteudo abaixo e responda SOMENTE em JSON valido.
Objetivo:
1) manter apenas o conteudo cristao relevante (sem menus, botoes, metadata de pagina, ruidos).
2) gerar 3 a 5 tags cristas em portugues.
3) sugerir 2 a 7 referencias biblicas pertinentes.

Retorne JSON com este formato exato:
{{
  "cleaned_text": "texto limpo sem resumo",
  "content_tags": ["fe", "amor", "humildade"],
  "bible_text_refs": ["Romans 1:17", "James 4:6"]
}}

Regras:
- Nao resumir o cleaned_text.
- Nao adicionar explicacoes fora do JSON.
- As tags devem ser curtas, em portugues, focadas em temas cristaos.

Conteudo:
---
{text}
---
"""


@dataclass
class LLMConfig:
    provider: str
    model: str
    timeout_s: int = 90
    temperature: float = 0.0
    min_ratio: float = 0.55


class LLMCleaner:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._cache: Dict[str, str] = {}
        self._metadata_cache: Dict[str, Dict] = {}

    @staticmethod
    def from_env(provider: Optional[str], model: Optional[str], timeout_s: int, temperature: float, min_ratio: float):
        p = (provider or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
        if not p:
            p = "openai"
        if p == "openai":
            default_model = "gpt-4o-mini"
        elif p == "anthropic":
            default_model = "claude-3-5-haiku-latest"
        elif p == "ollama":
            default_model = "llama3.1"
        else:
            raise ValueError(f"LLM provider invalido: {p}")
        m = (model or os.getenv("LLM_MODEL", default_model)).strip()
        return LLMCleaner(LLMConfig(provider=p, model=m, timeout_s=timeout_s, temperature=temperature, min_ratio=min_ratio))

    def clean_cell(self, text: str) -> Tuple[str, bool, str]:
        raw = str(text or "")
        if not raw.strip():
            return "", False, "empty"
        cache_key = f"{self.cfg.provider}|{self.cfg.model}|{raw}"
        if cache_key in self._cache:
            return self._cache[cache_key], True, "cache"

        if self.cfg.provider == "openai":
            candidate = self._openai_clean(raw)
        elif self.cfg.provider == "anthropic":
            candidate = self._anthropic_clean(raw)
        else:
            candidate = self._ollama_clean(raw)

        cleaned = (candidate or "").strip()
        if not cleaned:
            return raw, False, "empty_response"

        if len(raw) >= 500:
            ratio = len(cleaned) / max(1, len(raw))
            if ratio < self.cfg.min_ratio:
                return raw, False, f"ratio_guard:{ratio:.2f}"

        self._cache[cache_key] = cleaned
        return cleaned, cleaned != raw, "ok"

    def enrich_cell(self, text: str) -> Dict:
        raw = str(text or "").strip()
        if not raw:
            return {"cleaned_text": "", "content_tags": [], "bible_text_refs": []}
        cache_key = f"{self.cfg.provider}|{self.cfg.model}|meta|{raw}"
        if cache_key in self._metadata_cache:
            return self._metadata_cache[cache_key]

        if self.cfg.provider == "openai":
            content = self._openai_metadata(raw)
        elif self.cfg.provider == "anthropic":
            content = self._anthropic_metadata(raw)
        else:
            content = self._ollama_metadata(raw)

        parsed = self._parse_metadata_json(content)
        self._metadata_cache[cache_key] = parsed
        return parsed

    def _parse_metadata_json(self, content: str) -> Dict:
        text = str(content or "").strip()
        if not text:
            return {"cleaned_text": "", "content_tags": [], "bible_text_refs": []}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise RuntimeError("LLM metadata retornou JSON invalido.")
            data = json.loads(text[start : end + 1])

        cleaned_text = str(data.get("cleaned_text", "") or "").strip()
        tags = data.get("content_tags", [])
        refs = data.get("bible_text_refs", [])
        if not isinstance(tags, list):
            tags = []
        if not isinstance(refs, list):
            refs = []
        tags = [str(t).strip().lower() for t in tags if str(t).strip()]
        refs = [str(r).strip() for r in refs if str(r).strip()]
        return {
            "cleaned_text": cleaned_text,
            "content_tags": tags[:5],
            "bible_text_refs": refs[:7],
        }

    def _openai_clean(self, text: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY nao definido.")
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text)},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
        if resp.status_code >= 300:
            preview = resp.text[:300]
            raise RuntimeError(f"OpenAI falhou HTTP {resp.status_code}: {preview}")
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])

    def _openai_metadata(self, text: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY nao definido.")
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": METADATA_PROMPT_TEMPLATE.format(text=text)},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
        if resp.status_code >= 300:
            preview = resp.text[:300]
            raise RuntimeError(f"OpenAI metadata falhou HTTP {resp.status_code}: {preview}")
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])

    def _anthropic_clean(self, text: str) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY nao definido.")
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.cfg.model,
            "max_tokens": 8192,
            "temperature": self.cfg.temperature,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text)},
            ],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
        if resp.status_code >= 300:
            preview = resp.text[:300]
            raise RuntimeError(f"Anthropic falhou HTTP {resp.status_code}: {preview}")
        data = resp.json()
        chunks = data.get("content", [])
        parts = [c.get("text", "") for c in chunks if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(part for part in parts if part).strip()

    def _anthropic_metadata(self, text: str) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY nao definido.")
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.cfg.model,
            "max_tokens": 4096,
            "temperature": self.cfg.temperature,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": METADATA_PROMPT_TEMPLATE.format(text=text)}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
        if resp.status_code >= 300:
            preview = resp.text[:300]
            raise RuntimeError(f"Anthropic metadata falhou HTTP {resp.status_code}: {preview}")
        data = resp.json()
        chunks = data.get("content", [])
        parts = [c.get("text", "") for c in chunks if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(part for part in parts if part).strip()

    def _ollama_clean(self, text: str) -> str:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        url = f"{base}/api/chat"
        payload = {
            "model": self.cfg.model,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text)},
            ],
        }
        resp = requests.post(url, json=payload, timeout=self.cfg.timeout_s)
        if resp.status_code >= 300:
            preview = resp.text[:300]
            raise RuntimeError(f"Ollama falhou HTTP {resp.status_code}: {preview}")
        data = resp.json()
        msg = data.get("message") or {}
        return str(msg.get("content", "")).strip()

    def _ollama_metadata(self, text: str) -> str:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        url = f"{base}/api/chat"
        payload = {
            "model": self.cfg.model,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": METADATA_PROMPT_TEMPLATE.format(text=text)},
            ],
        }
        resp = requests.post(url, json=payload, timeout=self.cfg.timeout_s)
        if resp.status_code >= 300:
            preview = resp.text[:300]
            raise RuntimeError(f"Ollama metadata falhou HTTP {resp.status_code}: {preview}")
        data = resp.json()
        msg = data.get("message") or {}
        return str(msg.get("content", "")).strip()
