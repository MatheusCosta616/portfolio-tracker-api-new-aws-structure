# Entrega — análise em pt-BR, deduplicação e relatório

Branch `ajustes-sentiment-ai-banca`, 11 commits, 51 arquivos, **160/160 testes
passando**.

---

## 1. Diagnóstico

O motor **já tinha** léxico pt-BR, `detect_language()` e regras setoriais
bilíngues. O problema não era falta de suporte a português no motor.

Problemas reais encontrados:

1. O caminho da análise (`POST /portfolios/{id}/analyse` →
   `portfolios/tasks.py::analyse_portfolio`) instanciava **somente** o
   `YFinanceFetcher`, hardcoded. Yahoo Finance devolve matéria em inglês.
2. O `GoogleNewsFetcher`, que consulta com `hl=pt-BR&gl=BR`, existia e estava
   registrado, mas só alimentava a feed ao vivo (que não persiste nem analisa),
   e só para FII. No Celery Beat dependia de uma linha
   `NewsSource(slug='google_news')` que **não era criada em lugar nenhum do
   código**.
3. `_lexical_sentiment` unia `pt_br.POSITIVE_TERMS | en.POSITIVE_TERMS`
   independente do idioma — contaminação cruzada nos dois sentidos.
4. O VADER, treinado só em inglês, pontuava texto em português com peso 25%, e
   35% quando o idioma dava `unknown` — o que era fácil, porque os marcadores
   eram conjuntos de ~9 palavras.
5. **Bug de léxico:** `"juros"` estava em `NEGATIVE_TERMS`. "Petrobras aprova
   juros sobre capital próprio" — notícia de provento, positiva — pontuava
   negativo.
6. Deduplicação existia na aplicação, **não no banco**: sem `UniqueConstraint`,
   duas requisições simultâneas faziam o mesmo `SELECT` vazio e ambas inseriam.
7. `should_publish` republicava na fila **toda vez** que a linha estava
   `pending`.
8. Identidade da notícia era só `NewsArticle.url`. URLs de RSS carregam
   parâmetros de rastreamento que variam → a mesma matéria virava artigos
   diferentes.
9. A explicação era template: *"Impacto positivo estimado para Petrobras.
   Contexto setorial: energy; temas: earnings; sinais: word:lucro."*
10. Não existia integração com LLM, relatório persistido, modelo de feedback nem
    `LOGGING` no `settings.py`.

## 2. Causa de o português não estar sendo analisado

**O pipeline nunca entregava notícia em português ao motor.** Não era o motor
que ignorava pt-BR. Itens 1 e 2 acima. Os itens 3, 4 e 5 degradavam a qualidade
quando, por acaso, um texto em português chegava.

## 3. Arquitetura escolhida

```
resolve_language()          fonte > banco > detecção > fallback configurável
        │
        ▼
select_engine(language)     ponto único de escolha, testável
        │
        ├── PortugueseAnalysisEngine   léxico pt-BR, sem VADER, com negação
        ├── EnglishAnalysisEngine      léxico en + VADER (como antes)
        └── LlmAnalysisEngine ──► LlmProvider ──► Anthropic | OpenAI | Gemini
                     └── fallback obrigatório para o motor local do idioma
```

Núcleo de pontuação compartilhado (`heuristic.py`): relevância, tópicos e
regras setoriais são os mesmos; o que muda entre motores é o **léxico injetado**
e o uso ou não do VADER.

## 4. Arquivos alterados

**Modificados:** `news/models.py` (só a classe `Analysis`),
`portifolio_tracker_api/settings.py`, `portifolio_tracker_api/urls.py`,
`portfolios/tasks.py`, `.env.example`.

**Novos fora do módulo:** `news/migrations/0004_...py`, app `feedback/`.

**Dentro de `sentiment_ai/`:** `dedup.py`, `observability.py`, `testsettings.py`,
`test_migrations/`, `engine/{language,base,heuristic,local,english,portuguese,selector,report,llm_engine}.py`,
`llm/{base,config,prompt,providers,__init__}.py`, 4 arquivos de teste novos;
reescritos `services.py`, `tasks.py`, `engine/{analyzer,schemas,__init__}.py`,
léxicos e `rules.py`.

**Não alterados:** `docker-compose.yml`, `news/tasks.py`, `news/controller.py`,
`news/dto.py`, `news/fetchers/`, `portfolios/controller.py`, `users/`,
`notifications/`, `core/`, aplicativo Expo, `requirements.txt`, `qa.yml`.

## 5. Migrations

| Migration | O que faz | Rollback |
|---|---|---|
| `news/0004_analysis_language_report_dedup` | 10 colunas aditivas; remove duplicatas históricas; cria `uq_analise_art_tic_ver` | `migrate news 0003_analysis_queue_fields` |
| `feedback/0001_initial` | tabela `feedbacks` | `migrate feedback zero` |

Colunas novas: `language`, `engine`, `sentiment_label`, `sentiment_score`,
`relevance_score`, `report`, `news_fingerprint`, `llm_used`, `fallback_reason`,
`queued_at`. Todas nulas ou com padrão vazio — linhas antigas continuam válidas.

## 6. Variáveis de ambiente novas

```env
SENTIMENT_QUEUE=
SENTIMENT_FALLBACK_LANGUAGE=
LLM_ENABLED=false
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
LLM_BASE_URL=
LLM_TIMEOUT_SECONDS=
LLM_MAX_RETRIES=
LLM_LANGUAGES=
```

Todas com padrão seguro. Sem nenhuma delas o sistema roda com o motor local.
O `.env.example` traz só os nomes.

Nenhuma dependência nova: a integração de LLM usa `requests`, que já estava no
`requirements.txt`.

## 7. Testes executados

```
$ pytest --ds=sentiment_ai.testsettings -q
160 passed in 12.80s
```

126 testes novos + 34 pré-existentes, todos passando. Detalhe em
`PLANO-DE-TESTE.md`. Validado também:

```
$ python manage.py check                       -> 0 issues
$ python manage.py makemigrations --check       -> No changes detected
$ python manage.py migrate                      -> OK
$ python manage.py migrate news 0003_...        -> rollback OK
$ python manage.py migrate                      -> re-aplicação OK
```

## 8. Deduplicação — como explicar

> O sistema identifica cada análise pela combinação da notícia, do ativo e da
> versão do motor. Quando a mesma solicitação é enviada novamente, o resultado
> existente é reutilizado. Se a análise ainda estiver sendo processada, a API
> retorna o mesmo identificador, evitando tarefas duplicadas. Notícias apenas
> semelhantes, mas com conteúdo ou origem diferentes, continuam sendo analisadas
> separadamente.

A deduplicação é da **API e do banco**, não da IA. Quatro mecanismos:
`UniqueConstraint` em `(article, ticker, model_version)`; `get_or_create`
transacional com tratamento de `IntegrityError`; `queued_at`, que impede
republicar uma pendente já enfileirada; e `news_fingerprint`, que reconhece a
mesma matéria coletada com URLs diferentes. A versão do motor inclui provedor,
modelo e versão do prompt.

## 9. Comportamento quando a LLM falha

Timeout, 429, JSON inválido, 401, provedor fora do ar, resposta incompleta,
texto grande demais e erro inesperado: todos caem no motor local do mesmo
idioma. O resultado grava `llm_used=false` e `fallback_reason=<motivo>`, e o
relatório diz explicitamente que veio do motor local. **Nenhuma tarefa fica
presa em `pending`** — inclusive estouro de tempo, que marca `failed`.
Credencial rejeitada não é retentada (não melhora com retry).

## 10. Rodar localmente

```bash
docker compose up --build
pytest --ds=sentiment_ai.testsettings -q
```

## 11. Deploy na AWS

Respeita o processo que já existe. **Não foi feito deploy.**

```bash
ssh <vm>
cd <repo>
git fetch origin && git checkout ajustes-sentiment-ai-banca
# confira duplicatas antes (query em PLANO-DE-TESTE.md, B0)
docker compose build
docker compose up -d
docker compose logs api | grep -i "0004_analysis"
```

O serviço `api` já roda `python manage.py migrate --fake-initial` no boot, então
as duas migrations aplicam sozinhas. Nenhuma alteração na VPC, no roteamento ou
no `docker-compose.yml`.

## 12. Rollback

```bash
docker compose exec api python manage.py migrate news 0003_analysis_queue_fields
docker compose exec api python manage.py migrate feedback zero
git checkout main
docker compose up -d --build
```

Nenhum resultado é perdido: o campo `analise`, com o JSON completo, nunca é
tocado. A remoção de duplicatas históricas **não** é revertida.

## 13. Riscos e pendências

1. **A migration apaga linhas.** `_drop_duplicates` remove duplicatas
   históricas — é obrigatório para criar a constraint. Rode a query de
   conferência antes (B0).
2. **Oracle trata `''` como `NULL`.** Uma linha com `ticker` vazio escapa da
   constraint. Na prática `request_analysis` recusa ticker vazio, então não
   deve acontecer.
3. **Nota satura em +1,00** em manchetes muito positivas (vários termos fortes
   somados). Está dentro da faixa e é clampada, mas se a banca perguntar "por
   que deu 1,00", a resposta é essa. Dá para suavizar depois ajustando os pesos.
4. **`irrelevant` não existe no tipo do app.** `SentimentLabel` em
   `src/types/index.ts` declara só `positive | negative | neutral`, mas o motor
   emite `irrelevant` — e já emitia antes. Não quebra em runtime (TypeScript
   não valida em execução), mas é inconsistência a corrigir.
5. **O job de teste do CI depende de Oracle.** `qa.yml` roda `pytest` contra o
   banco dos secrets, que precisa permitir criar schema de teste. Uma linha
   (`DJANGO_SETTINGS_MODULE: sentiment_ai.testsettings`) deixaria o job
   determinístico — **não alterei**, é decisão de vocês.
6. **Celery Beat ainda não traz pt-BR.** `fetch_news_for_all_active_sources`
   depende de uma linha `NewsSource(slug='google_news', is_active=True)` no
   banco. A análise sob demanda agora cria essa linha sozinha, então depois do
   primeiro `POST /analyse` o Beat também passa a coletar em português. Se
   quiserem garantir antes, insiram a linha manualmente.
7. **`sentiment_ai/EXTERNAL_CHANGES.patch`** é resíduo da entrega anterior e
   está desatualizado. Deixei como estava.
8. **Credenciais do Oracle no `docker-compose.yml`** — você pediu para não
   mexer. Continuam lá.

## 14. Texto curto para a apresentação

> O sistema analisa notícias em português e em inglês. O idioma é identificado
> em quatro etapas — o que a fonte declara, o que já está no banco, a detecção
> pelo texto e um padrão configurável — e cada idioma tem seu próprio motor:
> português usa léxico e regras próprias, com tratamento de negação; inglês
> mantém o motor anterior com VADER. Opcionalmente um modelo de linguagem
> externo pode assumir a análise em português; se ele falhar por qualquer
> motivo, o motor local assume e o resultado registra qual dos dois produziu a
> análise.
>
> Cada análise é identificada pela combinação da notícia, do ativo e da versão
> do motor, com restrição de unicidade no banco de dados. Repetir a solicitação
> reaproveita o resultado; se ainda estiver processando, a API devolve o mesmo
> identificador. Notícias apenas semelhantes continuam sendo analisadas
> separadamente. A deduplicação é responsabilidade da API e do banco, não do
> modelo de linguagem.
>
> Cada resultado traz um relatório curto em português que informa a
> classificação, a nota, a relevância para o ativo e quais expressões do título
> ou do resumo justificaram o resultado.
