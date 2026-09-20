# Alterações fora do diretório `sentiment_ai/`

A integração continua desenhada para tocar o mínimo possível fora do módulo.
Este documento substitui a versão anterior e lista o estado atual.

## 1. `news/models.py` — somente a classe `Analysis`

`NewsSource` e `NewsArticle` **não** foram tocadas.

Campos adicionados, todos aceitando nulo ou com padrão vazio, para não quebrar
as linhas já gravadas:

| Campo | Para quê |
|---|---|
| `language` | idioma resolvido, consultável e reaproveitado pelo worker |
| `engine` | qual motor produziu a análise |
| `sentiment_label` | rótulo, para filtrar sem abrir o JSON |
| `sentiment_score` | nota |
| `relevance_score` | relevância |
| `report` | relatório curto em português |
| `news_fingerprint` | identidade canônica da notícia |
| `llm_used` | se a LLM externa produziu o resultado |
| `fallback_reason` | por que houve fallback, quando houve |
| `queued_at` | quando o ID foi publicado na fila |

E a constraint que garante a deduplicação no banco:

```python
models.UniqueConstraint(
    fields=['article', 'ticker', 'model_version'],
    name='uq_analise_art_tic_ver',
)
```

O nome é curto de propósito: Oracle 11g/12.1 limita identificadores a 30
caracteres.

## 2. `news/migrations/0004_analysis_language_report_dedup.py`

Migration nova. Adiciona as colunas, **remove duplicatas históricas** da tripla
`(article, ticker, model_version)` e só então cria a constraint — sem esse passo
do meio a constraint não pode ser criada numa base que já rodou em produção.

Rollback:

```bash
python manage.py migrate news 0003_analysis_queue_fields
```

A reversão remove a constraint e as colunas novas. Nenhum resultado é perdido: o
campo `analise`, que guarda o JSON completo, nunca é tocado. A remoção de linhas
duplicadas **não** é revertida — linhas apagadas não voltam.

## 3. `portifolio_tracker_api/settings.py`

* `INSTALLED_APPS` ganhou `'feedback'` (o `sentiment_ai` já estava lá);
* bloco de configuração do sentimento (`SENTIMENT_*`);
* bloco de configuração da LLM (`LLM_*`), tudo lido do ambiente;
* `LOGGING` estruturado — o projeto não tinha nenhum.

## 4. `portifolio_tracker_api/urls.py`

Uma linha: `path('api/feedback/', include('feedback.urls'))`.

## 5. `portfolios/tasks.py` — a correção do P0

`analyse_portfolio` instanciava **somente** o `YFinanceFetcher`, que devolve
matéria em inglês. Era por isso que o motor nunca via notícia em português: não
era o motor que ignorava pt-BR, era o pipeline que nunca entregava.

Agora a task percorre as fontes de `SENTIMENT_ANALYSIS_SOURCES`
(`yfinance` + `google_news`, o segundo consultado com `hl=pt-BR&gl=BR` pelo
próprio fetcher, que **não** foi alterado), deduplica URLs entre as fontes e
segue chamando `request_analysis` como antes. Uma fonte fora do ar não derruba a
análise inteira. O limite de tempo da task subiu de 90/120s para 240/300s,
alinhado ao `--soft-time-limit=240` já usado pelo worker geral.

## 6. `docker-compose.yml`

**Não foi alterado.** O serviço `sentiment-worker` já existia e continua válido.
Para ligar a LLM, acrescente as variáveis `LLM_*` ao serviço `sentiment-worker`.

## 7. App novo `feedback/`

App Django separado, isolado por exigência do próprio enunciado: nenhuma linha
dele importa `sentiment_ai`. Endpoints `POST /api/feedback/` e
`GET /api/feedback/list` (este restrito a staff).

## Arquivos que continuam intactos

* `news/tasks.py`
* `news/controller.py`
* `news/dto.py` — não foi preciso: o JSON completo já trafega no campo `result`,
  então os campos novos chegam ao cliente sem mudar o serializer
* `news/fetchers/` — inclusive o `GoogleNewsFetcher`
* `portfolios/controller.py` e `portfolios/dto.py`
* `users/`, `notifications/`, `core/`
* o aplicativo Expo
* `requirements.txt` da raiz — a integração de LLM usa `requests`, que já é
  dependência do projeto
* `docker-compose.yml`
* `.github/workflows/qa.yml`
