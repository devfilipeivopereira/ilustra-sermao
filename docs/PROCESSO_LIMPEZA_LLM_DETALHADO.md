# Processo Detalhado de Limpeza com LLM

Este documento descreve o fluxo completo implementado para limpar `body_text`, enriquecer metadados e preparar envio para a tabela `ilustracaoes_de_sermoes`.

## 1. Objetivo

- Limpar `body_text` celula a celula.
- Remover ruido de interface/metadados (ex.: botoes, labels de pagina).
- Manter apenas conteudo textual relevante.
- Gerar duas novas colunas:
  - `content_tags`: 3 a 5 tags cristas pertinentes e variadas.
  - `bible_text_refs`: referencias biblicas pertinentes ao conteudo.
- Pular LLM para tipos de conteudo `sermon/series`.

## 2. Arquivos envolvidos

- `limpeza/clean_content.py`
  - Pipeline principal de limpeza e enriquecimento.
- `limpeza/llm_cleaner.py`
  - Integra com OpenAI/Anthropic/Ollama.
  - Faz limpeza por chunk + enrichment (JSON com texto limpo, tags e refs).
- `limpeza/remove_fixed_phrase.py`
  - Pos-processamento local para remover frase fixa em JSONL.
- `limpeza/remove_phrase_supabase.py`
  - Pos-processamento direto no Supabase para remover frase fixa da tabela.
- `extrair/migrate_to_supabase.py`
  - Upsert para Supabase incluindo novas colunas.
- `extrair/supabase_ilustracaoes_de_sermoes.sql`
  - Schema atualizado com novas colunas.
- `api/_supabase.js` e `api/contents.js`
  - Sanitizacao e exposicao das novas colunas na API.

## 3. Fluxo implementado

1. Leitura JSONL de entrada.
2. Limpeza por regras:
  - `fix_mojibake`
  - normalizacao Unicode/whitespace
  - remocao de controles e HTML residual
  - remocao de ruido de UI (`--strict-relevance`)
3. Regra de exclusao de tipo para LLM:
  - `sermon`
  - `series`
  - `sermoncentral_sermon`
  - `sermoncentral_series`
4. Para tipos permitidos:
  - LLM limpa `body_text` por chunks (`--llm-chunk-chars`).
  - LLM faz enrichment em JSON:
    - `cleaned_text`
    - `content_tags`
    - `bible_text_refs`
5. Consolidacao final:
  - `content_tags` com 3-5 itens (priorizando variedade global).
  - `bible_text_refs` validadas para formato de referencia biblica.
6. Recalculo de `ai_text`.
7. Escrita JSONL final.

## 4. Novas colunas

- `content_tags` (texto CSV)
  - Tags cristas em portugues.
  - Diversidade ativa entre registros (evita repetir sempre as mesmas).
- `bible_text_refs` (texto CSV)
  - 2 a 7 referencias pertinentes.
  - Filtra ruido (UUIDs, tokens nao biblicos).

## 5. Comandos de execucao

### 5.1 Limpeza completa local

```powershell
$env:OPENAI_API_KEY="SUA_CHAVE"
python limpeza\clean_content.py `
  --input data\limpeza\ilustracaoes_de_sermoes_cleaned.jsonl `
  --output data\limpeza\ilustracaoes_de_sermoes_cleaned_llm_full_v2.jsonl `
  --use-llm `
  --llm-provider openai `
  --llm-model gpt-4o-mini `
  --llm-min-chars 1 `
  --llm-chunk-chars 12000 `
  --strict-relevance `
  --progress-every 20
```

### 5.2 Remocao de frase fixa no JSONL final

```powershell
python limpeza\remove_fixed_phrase.py `
  --input data\limpeza\ilustracaoes_de_sermoes_cleaned_llm_full_v2.jsonl `
  --output data\limpeza\ilustracaoes_de_sermoes_cleaned_llm_full_v2_no_phrase.jsonl
```

Frase removida:
- `View all articles by SermonCentral.com`
- variante com espaco: `View all articles by SermonCentral .com`

### 5.3 Upsert para Supabase

```powershell
$env:SOURCE_JSONL="data/limpeza/ilustracaoes_de_sermoes_cleaned_llm_full_v2_no_phrase.jsonl"
python extrair\migrate_to_supabase.py
```

## 6. Remocao direta da frase no Supabase (opcional)

Se precisar limpar o que ja esta publicado sem refazer pipeline inteiro:

```powershell
$env:SUPABASE_URL="..."
$env:SUPABASE_SERVICE_ROLE_KEY="..."
python limpeza\remove_phrase_supabase.py
```

Esse script:
- varre a tabela paginada
- remove a frase dos campos `body_text,summary,ai_text,citations`
- aplica upsert somente nos registros alterados

## 7. SQL de schema

As colunas novas adicionadas no schema:

- `content_tags text`
- `bible_text_refs text`

Arquivo:
- `extrair/supabase_ilustracaoes_de_sermoes.sql`

## 8. API e filtros

- Sanitizacao de campos CSV-like atualizada em `api/_supabase.js`.
- `api/contents.js` agora inclui:
  - `content_tags`
  - `bible_text_refs`
- Busca textual (`search`) inclui as novas colunas.

## 9. Observacoes operacionais

- O processamento completo com LLM pode durar horas e ter custo alto.
- Use `--llm-limit` para validar com amostra antes.
- Para monitorar em tempo real:

```powershell
Get-Content data\limpeza\llm_full.log -Wait
```

- Em caso de chave exposta, gere uma nova imediatamente.

## 10. Checklist final

1. Rodar limpeza completa.
2. Rodar `remove_fixed_phrase.py`.
3. Validar amostra antes/depois.
4. Rodar upsert.
5. Validar API retornando `content_tags` e `bible_text_refs`.
