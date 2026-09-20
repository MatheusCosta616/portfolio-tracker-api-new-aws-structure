# Plano de teste — análise em pt-BR, deduplicação e relatório

Branch: `ajustes-sentiment-ai-banca`

Duas camadas. A **camada A** já foi executada e tem resultado registrado. A
**camada B** precisa do Oracle da FIAP e do RabbitMQ reais, então tem que ser
rodada por vocês, na VM da AWS ou com `docker compose` local.

---

## Camada A — automatizada (já executada: 160/160)

```bash
pytest --ds=sentiment_ai.testsettings -q
```

Não acessa rede, não acessa Oracle. Cobertura:

| Grupo | Testes | O que prova |
|---|---|---|
| `DetectLanguageTests` | 10 | pt-BR claro, com acento, título curto, inglês, ticker misturado, idioma ausente, texto vazio |
| `ResolveLanguageChainTests` | 6 | a ordem fonte → banco → detecção → fallback, e que ausência de idioma **não** vira inglês |
| `NormalizeLanguageCodeTests` | 3 | `pt`, `pt_BR`, `PT-br`, `en-US` |
| `LexiconIsolationTests` | 4 | léxico pt não pontua texto em inglês e vice-versa; negação; intensificador |
| `PortugueseAnalysisTests` | 7 | positiva, negativa, irrelevante, faixa de score, texto vazio, **"juros sobre capital próprio" positivo**, negação no título |
| `EnglishAnalysisTests` | 2 | o fluxo em inglês continua como era |
| `EngineSelectionTests` | 7 | motor certo por idioma; LLM desligada ou mal configurada devolve motor local |
| `ReportTests` | 3 | relatório cita elementos da notícia e não usa frase genérica |
| `LlmEngineTests` | 10 | saída convertida para o modelo interno; timeout, JSON inválido, 429, 401, provedor fora do ar e erro inesperado caem no motor local; versão muda com modelo/provedor; chave nunca aparece |
| `LlmResponseParsingTests` | 10 | JSON estrito, cerca de código, texto fora do JSON, resposta vazia, campo não numérico, score fora da faixa, rótulo inválido, `reasoning` ausente e truncamento |
| `CanonicalUrlTests` + `FingerprintTests` | 8 | URL canônica e impressão digital; notícias parecidas mas diferentes não colidem |
| `DeduplicationFlowTests` | 15 | mesmo registro, ticker diferente, versão nova, **4 threads simultâneas**, `IntegrityError` do banco, pendente não republicada, concluída não reprocessa, matéria repetida em outra URL reaproveita |
| `SentimentQueueFlowTests` | 10 | signal → fila → worker; colunas gravadas; motor não roda de novo para concluída; estouro de tempo vira `failed` |
| `PortfolioAnalysisPipelineTests` | 2 | **o P0**: a análise da carteira passa a receber notícia em pt-BR e em inglês; fonte fora do ar não derruba |
| `AnalysisContractTests` | 10 | contrato antigo do app preservado; os quatro status; 404/400 sem vazar detalhe |
| `FeedbackApiTests` | 7 | envio, campos opcionais, nota fora da faixa, listagem só para staff |
| Suíte pré-existente | 34 | `users`, `news`, `portfolios`, `notifications` continuam passando |

---

## Camada B — manual, com infraestrutura real

### B0. Preparação

```bash
git fetch origin && git checkout ajustes-sentiment-ai-banca
docker compose build
```

**Antes de subir, tire uma foto das análises duplicadas que a migration vai
apagar:**

```sql
SELECT article_id, ticker, model_version, COUNT(*) AS qtd
FROM analises
GROUP BY article_id, ticker, model_version
HAVING COUNT(*) > 1;
```

Se o resultado for vazio, a migration não apaga nada.

### B1. Migration aplica no Oracle

```bash
docker compose up -d
docker compose logs api | grep -i "0004_analysis"
```

**Esperado:** `Applying news.0004_analysis_language_report_dedup... OK` e
`Applying feedback.0001_initial... OK`.

**Ponto de atenção do Oracle:** o nome da constraint é `uq_analise_art_tic_ver`
(22 caracteres) justamente para caber no limite de 30 do Oracle 11g/12.1. Se
der erro de identificador, é outro problema — mande o log.

Confirme no banco:

```sql
SELECT constraint_name, constraint_type FROM user_constraints
WHERE table_name = 'ANALISES';
SELECT column_name FROM user_tab_columns WHERE table_name = 'ANALISES';
```

### B2. Notícia em português chega na análise — o teste principal

1. Crie uma carteira com `PETR4`, `VALE3` e um FII (`HGLG11`).
2. `POST /api/portfolios/{id}/analyse` → deve responder **202** com `task_id`.
3. Acompanhe: `docker compose logs -f celery-worker sentiment-worker`.
4. `GET /api/portfolios/{id}/analyses`.

**Esperado:** pelo menos uma análise com `result.language == "pt-BR"` e
`result.engine == "rules-ptbr"`. Antes desta branch **nenhuma** vinha em
português.

```sql
SELECT language, engine, COUNT(*) FROM analises GROUP BY language, engine;
```

### B3. Relatório fundamentado

Abra uma análise em pt-BR e leia `result.report`. **Esperado:** cita expressões
que estão no título ou no resumo, com acento, e termina dizendo qual motor
produziu. **Não pode** aparecer nada do tipo "a IA analisou a notícia".

No app: a tela de análises lê `explanation`, que agora recebe o mesmo texto.
Confirme que o texto melhorou **sem nenhuma alteração no aplicativo**.

### B4. Idempotência de verdade, com RabbitMQ

1. `POST /analyse` na mesma carteira **três vezes seguidas**, rápido.
2. Conte as análises:

```sql
SELECT article_id, ticker, model_version, COUNT(*)
FROM analises GROUP BY article_id, ticker, model_version HAVING COUNT(*) > 1;
```

**Esperado:** nenhuma linha. Nos logs, `analysis_already_queued` ou
`analysis_reused` em vez de `analysis_published` repetido.

3. Na interface do RabbitMQ (`http://<host>:15672`, fila `sentiment_analysis`),
   confirme que não houve uma mensagem por requisição.

### B5. Fila e worker

1. `docker compose stop sentiment-worker`
2. `POST /analyse` → as linhas ficam `pending` e as mensagens acumulam na fila.
3. `docker compose start sentiment-worker` → as linhas viram `completed`.

**Esperado:** nada fica preso em `pending` depois que o worker volta.

### B6. Falha do broker

1. `docker compose stop rabbitmq`
2. `POST /analyse`
3. **Esperado:** log `analysis_publish_failed`, linha em `pending` com
   `queued_at` nulo.
4. `docker compose start rabbitmq` e `POST /analyse` de novo →
   `analysis_published`, agora sim.

### B7. LLM externa (só se forem ligar)

Acrescente ao serviço `sentiment-worker` no `docker-compose.yml`:

```yaml
      - LLM_ENABLED=true
      - LLM_PROVIDER=anthropic     # ou openai / gemini
      - LLM_MODEL=<modelo>
      - LLM_API_KEY=<chave>
```

| Cenário | Como provocar | Esperado |
|---|---|---|
| Sucesso | chave válida | `llm_used=true`, `engine` começa com `llm-` |
| Credencial errada | chave inválida | `fallback_reason=auth_error`, `llm_used=false`, análise **conclui** |
| Provedor fora do ar | `LLM_BASE_URL=https://127.0.0.1:9` | `fallback_reason=unavailable`, análise conclui |
| Timeout | `LLM_TIMEOUT_SECONDS=1` | `fallback_reason=timeout`, análise conclui |
| Reuso | repetir o `POST` | `analysis_reused`, **sem** nova chamada ao provedor |

Depois, confirme que a chave **não** aparece em `docker compose logs`:

```bash
docker compose logs sentiment-worker | grep -i -E "api[_-]?key|sk-|authorization"
```

**Esperado:** nenhuma saída.

### B8. Feedback

```
POST /api/feedback/   {"rating": 5, "made_sense": "yes", "app_version": "1.0.0"}
POST /api/feedback/   {"rating": 9}          -> 400
GET  /api/feedback/list                       -> 403 para usuário comum
GET  /api/feedback/list                       -> 200 para staff
```

### B9. Regressão do aplicativo

Rode o app apontando para a API nova e confira: login, carteiras, ativos,
notícias, análises e push. Nenhum campo do contrato foi removido ou renomeado,
então a expectativa é zero alteração de comportamento — exceto o texto da
análise, que fica melhor.

---

## Critério de aceite

A entrega passa se: B1 aplica, B2 mostra pelo menos uma análise `pt-BR`, B3 traz
relatório fundamentado, B4 não produz duplicata, B5 e B6 não deixam nada preso
em `pending`, e B9 não regride nada no app.
