# Estratégia Detalhada de Limpeza de Conteúdo

Documento completo sobre a limpeza das colunas de conteúdo no Supabase, incluindo fluxos de download/limpeza/migração e uso de modelos LLM no projeto.

---

## 1. Contexto e Objetivos

### 1.1 Tabela e colunas

A tabela `ilustracaoes_de_sermoes` no Supabase armazena histórias, ilustrações, citações, liturgia e séries. As colunas de **conteúdo textual** são as que mais exigem limpeza:

| Coluna | Descrição | Risco de sujeira |
|--------|-----------|------------------|
| `body_text` | Corpo principal do texto | Alto – HTML residual, mojibake, espaços |
| `summary` | Resumo/sinopse | Médio |
| `ai_text` | Texto concatenado para busca/IA | Médio – derivado de outros campos |
| `citations` | Citações | Médio |
| `categories`, `top_level_categories` | Categorias em CSV | Baixo |
| `bible_references`, `keywords`, `auto_tags` | Metadados em CSV | Baixo |

### 1.2 Objetivos

1. **Integridade**: Remover caracteres inválidos, mojibake e HTML residual
2. **Consistência**: Normalizar espaços em branco e quebras de linha
3. **Performance**: Evitar textos excessivamente longos que impactem busca e storage
4. **Qualidade**: Garantir que o conteúdo exibido e indexado seja legível

---

## 2. Fluxo: Baixar → Limpar → Migrar

### 2.1 Visão geral

É possível executar o fluxo completo **baixar dados → limpar localmente → migrar de volta ao Supabase**. Duas variantes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FLUXO A: Fonte original (JSONL da extração)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  extract_content_pipeline.py  →  JSONL (data/tpw/tpw_content_complete.jsonl) │
│              ↓                                                              │
│  script de limpeza  →  JSONL limpo (ex: data/limpeza/cleaned.jsonl)         │
│              ↓                                                              │
│  migrate_to_supabase.py  SOURCE_JSONL=cleaned.jsonl                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  FLUXO B: Dados já no Supabase                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  script de download (REST API paginada)  →  JSONL                            │
│              ↓                                                              │
│  script de limpeza  →  JSONL limpo                                          │
│              ↓                                                              │
│  migrate_to_supabase.py  →  upsert de volta (on_conflict=uuid)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo A – Fonte original

**Quando usar**: Quando o JSONL da extração ainda existe e é a fonte de verdade.

**Passos**:

1. Rodar extração (se necessário): `python extrair/extract_content_pipeline.py`
2. Rodar limpeza: `python limpeza/clean_content.py --input data/tpw/tpw_content_complete.jsonl --output data/limpeza/cleaned.jsonl`
3. Migrar: `SOURCE_JSONL=data/limpeza/cleaned.jsonl python extrair/migrate_to_supabase.py`

### 2.3 Fluxo B – Baixar do Supabase

**Quando usar**: Quando o Supabase é a única fonte atual dos dados.

**Passos**:

1. Baixar: `python limpeza/download_from_supabase.py --output data/limpeza/backup.jsonl`
2. Limpar: `python limpeza/clean_content.py --input data/limpeza/backup.jsonl --output data/limpeza/cleaned.jsonl`
3. Migrar de volta: `SOURCE_JSONL=data/limpeza/cleaned.jsonl python extrair/migrate_to_supabase.py`

O `migrate_to_supabase.py` faz upsert por `uuid`, então os registros limpos sobrescrevem os existentes.

---

## 3. Estratégia Geral (4 Fases)

### Fase 1: Diagnóstico

**Objetivo**: Entender o estado atual dos dados antes de alterar.

- **1.1** Exportar amostra (ex.: 500–1000 registros) via API ou script
- **1.2** Analisar:
  - Presença de HTML (`<p>`, `<br>`, `<strong>`, etc.)
  - Mojibake (ex.: `Ã¢â‚¬â„¢` em vez de `'`)
  - Caracteres de controle (null bytes, tabs excessivos)
  - Tamanho médio/máximo de `body_text` e `ai_text`
  - Campos vazios vs. `null`
- **1.3** Documentar padrões encontrados e priorizar colunas

**Ferramentas sugeridas**: Script Python com `requests` + análise com regex/BeautifulSoup.

### Fase 2: Definição das Regras de Limpeza

| Regra | Aplicar em | Descrição |
|-------|------------|-----------|
| Mojibake | `body_text`, `summary`, `citations` | Substituir sequências conhecidas (`fix_mojibake` em `extract_content_pipeline.py`) |
| Normalização de espaços | Todas as colunas de texto | `strip()`, colapsar múltiplos espaços, normalizar `\n` |
| Remoção de HTML | `body_text`, `summary` | Extrair texto puro (BeautifulSoup) ou regex para tags comuns |
| Limite de tamanho | `body_text`, `ai_text` | Definir max (ex.: 100k caracteres) e truncar com aviso |
| Unicode | Todas | `unicodedata.normalize("NFC", text)` para consistência |
| Caracteres de controle | Todas | Remover `\x00`, `\r` desnecessários |

### Fase 3: Implementação

- **Opção A**: Script de migração em lote (recomendado para dados atuais)
- **Opção B**: Limpeza na ingestão (pipeline) para dados futuros
- **Opção C**: Híbrido – migração única + limpeza na ingestão

### Fase 4: Validação e Rollback

- Backup da tabela antes da migração
- Executar em staging primeiro
- Comparar amostras antes/depois
- Validar no frontend
- Ter script de rollback

---

## 4. Uso de Modelos LLM no Projeto

### 4.1 Papel dos LLMs na limpeza

Os LLMs podem complementar a limpeza baseada em regras em cenários como:

| Caso de uso | Descrição | Prioridade |
|-------------|-----------|------------|
| Correção de mojibake complexo | Sequências que regras fixas não cobrem | Opcional |
| Extração de texto de HTML malformado | Quando BeautifulSoup falha | Opcional |
| Geração/melhoria de `summary` | Resumir `body_text` quando vazio ou ruim | Opcional |
| Refinamento de `auto_tags` | Sugerir tags temáticas além do `content_taxonomy.py` | Opcional |
| Validação semântica | Detectar conteúdo incoerente ou corrompido | Opcional |

A limpeza **deve** funcionar sem LLM. O LLM é uma camada opcional para casos difíceis.

### 4.2 Configuração de ambiente

Criar/atualizar `.env` com variáveis para provedores de LLM:

```bash
# LLM – opcional (se não definido, limpeza roda só com regras)
OPENAI_API_KEY=sk-...
# ou
ANTHROPIC_API_KEY=sk-ant-...
# ou (modelos locais)
OLLAMA_BASE_URL=http://localhost:11434

# Qual provedor usar: openai | anthropic | ollama
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini   # ou claude-3-haiku, llama3, etc.
```

### 4.3 Estrutura sugerida para integração LLM

```
limpeza/
├── clean_content.py          # Limpeza baseada em regras (obrigatório)
├── llm_cleaner.py            # Módulo opcional que chama LLM
├── download_from_supabase.py # Download paginado
└── ESTRATEGIA_LIMPEZA_DETALHADA.md
```

### 4.4 Interface do módulo LLM

O `llm_cleaner.py` deve expor funções que recebem texto e retornam texto limpo, com fallback para o original em caso de erro:

```python
# Exemplo de interface
def llm_fix_mojibake(text: str) -> str:
    """Envia texto ao LLM para corrigir mojibake. Retorna original se API falhar."""
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        return text  # Sem API key = não usar LLM
    # ... chamada à API ...
    return cleaned_or_original
```

### 4.5 Provedores suportados

| Provedor | Biblioteca | Variável de ambiente | Modelo sugerido |
|----------|-------------|----------------------|-----------------|
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` (barato, rápido) |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-haiku-20240307` |
| Ollama (local) | `requests` ou `ollama` | `OLLAMA_BASE_URL` | `llama3`, `mistral` |

### 4.6 Instalação de dependências

```bash
# Limpeza básica (sem LLM)
pip install requests beautifulsoup4

# Com OpenAI
pip install openai

# Com Anthropic
pip install anthropic

# Com Ollama (local)
# Nenhuma lib extra; requests já basta
```

### 4.7 Uso no script de limpeza

O `clean_content.py` deve ter um flag para ativar o LLM:

```bash
# Apenas regras (padrão)
python limpeza/clean_content.py --input in.jsonl --output out.jsonl

# Com LLM para casos difíceis (quando API key configurada)
python limpeza/clean_content.py --input in.jsonl --output out.jsonl --use-llm

# Limitar chamadas LLM (ex.: só primeiros 100 registros problemáticos)
python limpeza/clean_content.py --input in.jsonl --output out.jsonl --use-llm --llm-limit 100
```

### 4.8 Prompts sugeridos para LLM

**Correção de mojibake**:
```
Corrija possíveis erros de encoding (mojibake) no texto abaixo. 
Retorne APENAS o texto corrigido, sem explicações.
Texto:
---
{text}
---
```

**Geração de summary**:
```
Resuma o texto abaixo em 1-3 frases em português. Seja conciso.
Texto:
---
{body_text}
---
Resumo:
```

**Refinamento de tags**:
```
Dado o título e o corpo do texto, sugira 2-4 tags temáticas em português (ex: tema:fe, tema:amor).
Retorne apenas as tags separadas por vírgula.
Título: {title}
Texto: {body_text[:500]}...
Tags:
```

### 4.9 Custos e rate limiting

- Usar modelos menores (`gpt-4o-mini`, `claude-3-haiku`) para reduzir custo
- Processar em lotes com `--llm-limit` para testes
- Adicionar `time.sleep()` entre chamadas para evitar rate limit
- Considerar Ollama para processamento local sem custo de API

---

## 5. Ordem de Execução Recomendada

1. **Diagnóstico** → Documentar o que existe hoje
2. **Backup** → Exportar dados críticos (Fluxo B passo 1)
3. **Implementar funções de limpeza** → Reutilizar `fix_mojibake`, `normalize_whitespace` do pipeline
4. **Script de migração** → Aplicar em lotes com log
5. **Validação** → Testes manuais e automatizados
6. **Integrar no pipeline** → Evitar nova sujeira em futuras migrações
7. **(Opcional)** Integrar LLM para casos que regras não resolvem

---

## 6. Referências no Código

- `extrair/extract_content_pipeline.py`: `fix_mojibake`, `normalize_whitespace`, `as_text`, `render_rich_text`
- `extrair/content_taxonomy.py`: normalização Unicode (NFKD), classificação por palavras-chave
- `extrair/migrate_to_supabase.py`: upsert a partir de JSONL
- `api/_supabase.js`: `sanitizeRecord`, `normalizeCsvLike`
- `extrair/supabase_ilustracaoes_de_sermoes.sql`: schema da tabela

---

## 7. Próximos Passos Concretos

1. Criar `limpeza/clean_content.py` com funções de limpeza e `--dry-run`
2. Criar `limpeza/download_from_supabase.py` para Fluxo B
3. Executar diagnóstico em amostra real
4. Ajustar regras conforme achados
5. Rodar migração em produção com backup prévio
6. (Opcional) Implementar `limpeza/llm_cleaner.py` e integrar com `--use-llm`
