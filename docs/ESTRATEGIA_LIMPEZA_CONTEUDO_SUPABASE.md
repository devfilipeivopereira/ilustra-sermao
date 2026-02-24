# Estratégia de Limpeza das Colunas de Conteúdo no Supabase

## Contexto

A tabela `ilustracaoes_de_sermoes` no Supabase armazena histórias, ilustrações, citações, liturgia e séries. As colunas de **conteúdo textual** são as que mais exigem limpeza:

| Coluna | Descrição | Risco de sujeira |
|--------|-----------|------------------|
| `body_text` | Corpo principal do texto | Alto – HTML residual, mojibake, espaços |
| `summary` | Resumo/sinopse | Médio |
| `ai_text` | Texto concatenado para busca/IA | Médio – derivado de outros campos |
| `citations` | Citações | Médio |
| `categories`, `top_level_categories` | Categorias em CSV | Baixo |
| `bible_references`, `keywords`, `auto_tags` | Metadados em CSV | Baixo |

---

## Objetivos da Limpeza

1. **Integridade**: Remover caracteres inválidos, mojibake e HTML residual
2. **Consistência**: Normalizar espaços em branco e quebras de linha
3. **Performance**: Evitar textos excessivamente longos que impactem busca e storage
4. **Qualidade**: Garantir que o conteúdo exibido e indexado seja legível

---

## Estratégia Geral (4 Fases)

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

---

### Fase 2: Definição das Regras de Limpeza

**Objetivo**: Especificar exatamente o que será aplicado em cada coluna.

| Regra | Aplicar em | Descrição |
|-------|------------|-----------|
| Mojibake | `body_text`, `summary`, `citations` | Substituir sequências conhecidas (já existe `fix_mojibake` em `extract_content_pipeline.py`) |
| Normalização de espaços | Todas as colunas de texto | `strip()`, colapsar múltiplos espaços, normalizar `\n` |
| Remoção de HTML | `body_text`, `summary` | Extrair texto puro (BeautifulSoup) ou regex para tags comuns |
| Limite de tamanho | `body_text`, `ai_text` | Definir max (ex.: 100k caracteres) e truncar com aviso |
| Unicode | Todas | `unicodedata.normalize("NFC", text)` para consistência |
| Caracteres de controle | Todas | Remover `\x00`, `\r` desnecessários |

**Decisões a tomar**:
- Manter ou remover quebras de linha em `body_text`?
- Truncar ou rejeitar registros com `body_text` muito grande?
- Atualizar `ai_text` automaticamente após limpar `body_text`/`summary`?

---

### Fase 3: Implementação

**Opções de abordagem**:

#### Opção A: Script de migração em lote (recomendado)

- Script Python que:
  1. Lê registros do Supabase (REST API ou `supabase-py`)
  2. Aplica funções de limpeza por coluna
  3. Faz PATCH em lotes (ex.: 50–100 por vez)
  4. Gera log de alterações (uuid, coluna, antes/depois)
- **Vantagem**: Controle total, rollback possível via backup
- **Desvantagem**: Requer execução manual ou agendada

#### Opção B: Limpeza na ingestão (pipeline)

- Integrar as funções de limpeza em:
  - `extrair/extract_content_pipeline.py` (TPW)
  - `sermoncentral/sermoncentral_pipeline.py`
  - `extrair/migrate_to_supabase.py`
- **Vantagem**: Novos dados já chegam limpos
- **Desvantagem**: Não corrige dados já existentes

#### Opção C: Híbrido

- **Migração única** (Opção A) para dados atuais
- **Limpeza na ingestão** (Opção B) para dados futuros

---

### Fase 4: Validação e Rollback

- **4.1** Backup da tabela antes da migração (export JSONL ou dump SQL)
- **4.2** Executar em ambiente de staging primeiro, se disponível
- **4.3** Comparar amostras antes/depois (checksum, contagem de caracteres)
- **4.4** Validar no frontend: listagem, busca, modal de detalhe
- **4.5** Ter script de rollback (restaurar de backup) em caso de problema

---

## Ordem de Execução Sugerida

1. **Diagnóstico** → Documentar o que existe hoje
2. **Backup** → Exportar dados críticos
3. **Implementar funções de limpeza** → Reutilizar `fix_mojibake`, `normalize_whitespace` do pipeline
4. **Script de migração** → Aplicar em lotes com log
5. **Validação** → Testes manuais e automatizados
6. **Integrar no pipeline** → Evitar nova sujeira em futuras migrações

---

## Referências no Código

- `extrair/extract_content_pipeline.py`: `fix_mojibake`, `normalize_whitespace`, `as_text`, `render_rich_text`
- `extrair/content_taxonomy.py`: normalização Unicode (NFKD)
- `api/_supabase.js`: `sanitizeRecord`, `normalizeCsvLike` (para campos CSV)
- `extrair/supabase_ilustracaoes_de_sermoes.sql`: schema da tabela

---

## Próximos Passos Concretos

1. Criar script `extrair/clean_supabase_content.py` com funções de limpeza
2. Adicionar modo `--dry-run` para simular sem alterar
3. Executar diagnóstico em amostra real
4. Ajustar regras conforme achados
5. Rodar migração em produção com backup prévio
