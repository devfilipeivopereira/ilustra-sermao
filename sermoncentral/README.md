# SermonCentral Pipeline

Pipeline completo para extração e organização de conteúdos do SermonCentral, pronto para uso no Supabase e frontend no Vercel.

## Tipos de conteúdo cobertos

- `illustrations`
- `sermons`
- `series`
- `articles`

Cada item é normalizado para um schema único, com `content_type`:

- `sermoncentral_illustration`
- `sermoncentral_sermon`
- `sermoncentral_series`
- `sermoncentral_article`

## Arquivos principais

- `sermoncentral_pipeline.py`: crawler + normalização + tags + export.
- `migrate_sermoncentral_to_supabase.py`: upsert em lote para Supabase.
- `sermoncentral_extraction_package.zip` e scripts antigos: referência histórica.

## Saídas geradas

Por padrão (prefixo `sermoncentral_complete`):

- `data/sermoncentral/sermoncentral_complete.json`
- `data/sermoncentral/sermoncentral_complete.jsonl`
- `data/sermoncentral/sermoncentral_complete.csv`
- `data/sermoncentral/sermoncentral_complete.sqlite` (tabela `records`)

## Variáveis de ambiente (extração)

- `SERMONCENTRAL_BASE_URL` (default: `https://www.sermoncentral.com`)
- `SERMONCENTRAL_EMAIL` (opcional)
- `SERMONCENTRAL_PASSWORD` (opcional)
- `SERMONCENTRAL_OUTPUT_PREFIX` (recomendado: `data/sermoncentral/sermoncentral_complete`)
- `SERMONCENTRAL_DB` (recomendado: `data/sermoncentral/sermoncentral_complete.sqlite`)
- `SERMONCENTRAL_MAX_LIST_PAGES` (default: `120`)
- `SERMONCENTRAL_MAX_DETAIL_ITEMS` (default: `0`, sem limite)
- `SERMONCENTRAL_SOURCES` (default: `illustrations,sermons,series,articles`)
- `SERMONCENTRAL_DELAY` (default: `0.5`)
- `SERMONCENTRAL_TIMEOUT` (default: `45`)

## Rodar extração

```powershell
python sermoncentral\sermoncentral_pipeline.py
```

Execução de teste (rápida):

```powershell
$env:SERMONCENTRAL_MAX_LIST_PAGES="3"
$env:SERMONCENTRAL_MAX_DETAIL_ITEMS="30"
python sermoncentral\sermoncentral_pipeline.py
```

## Migrar para Supabase (mesma tabela do frontend)

Por padrão envia para `ilustracaoes_de_sermoes` usando `uuid` como upsert key.

```powershell
$env:SUPABASE_URL="https://seu-dominio-supabase"
$env:SUPABASE_SERVICE_ROLE_KEY="sua_service_role_key"
$env:SUPABASE_TABLE="ilustracaoes_de_sermoes"
$env:SOURCE_JSONL="data/sermoncentral/sermoncentral_complete.jsonl"
python sermoncentral\migrate_sermoncentral_to_supabase.py
```

## Integração com frontend/Vercel

O frontend/API atual já lê da tabela `ilustracaoes_de_sermoes`.

Depois da migração, os novos conteúdos aparecerão automaticamente, filtráveis por:

- tipo (`content_type`)
- autor
- categorias
- tags (`auto_tags`)
- busca textual

## Observações

- Sem login, parte do conteúdo pode vir truncada (dependendo da página).
- Mantenha delays e retries para evitar bloqueio/rate limit.
- Não versionar saídas grandes (`.csv/.json/.jsonl/.sqlite`) no Git.
