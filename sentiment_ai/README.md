# Sentiment AI — worker de análise de sentimento

Consumidor Celery dedicado que analisa notícias em **português brasileiro** e
**inglês**. Não cria tabelas próprias: usa a tabela existente `analises` do app
`news`.

---

## Fluxo

1. A API associa uma `NewsArticle` a um ou mais `Asset` (`article.tickers.add(...)`),
   ou a task `analyse_portfolio` chama `request_analysis` diretamente.
2. `services.request_analysis` resolve o **idioma**, escolhe o **motor** e calcula
   a **versão lógica** do motor.
3. Uma linha em `analises` é criada (ou reaproveitada) para a tripla
   `notícia + ticker + versão do motor`.
4. Só o ID dessa linha vai para a fila RabbitMQ `sentiment_analysis`.
5. O worker `sentiment-worker` processa um pedido por vez.
6. A mesma linha vira `processing` e depois `completed` ou `failed`.
7. O JSON completo fica no campo `analise`; o relatório curto também vai para a
   coluna `report`.

---

## Idioma

A identificação segue esta ordem, e **nenhuma etapa assume inglês por omissão**:

| # | Origem | Onde |
|---|---|---|
| 1 | Idioma declarado pela fonte | `SENTIMENT_SOURCE_LANGUAGES` (ex.: `google_news` → `pt-BR`) |
| 2 | Idioma já gravado no banco | `Analysis.language` |
| 3 | Detecção por título + resumo | `engine/language.py` |
| 4 | Fallback configurável | `SENTIMENT_FALLBACK_LANGUAGE` (padrão `pt-BR`) |

A detecção trata acentos, cedilha, Unicode, pontuação, texto curto, títulos que
misturam ticker com palavras em português e termos financeiros em inglês dentro
de texto em português. Formas de ticker (`PETR4`, `HGLG11`, `BTC-USD`,
`VALE3.SA`) são removidas antes da contagem. Sem evidência suficiente o
resultado é `unknown`, e só então o fallback entra — de forma explícita.

---

## Motores

```
AnalysisEngine
├── EnglishAnalysisEngine      léxico en + VADER
├── PortugueseAnalysisEngine   léxico pt-BR, sem VADER, com negação
└── LlmAnalysisEngine          LLM externa, com fallback para os de cima
```

A escolha acontece em **um único lugar**, `engine/selector.py::select_engine`.
Não há condicional de idioma espalhada pelo código.

Diferenças do motor de português:

* usa **somente** o léxico pt-BR — antes os dois léxicos eram unidos e se
  contaminavam;
* **não** usa VADER, que é treinado em inglês e só injetava ruído;
* trata negação (`"não registrou prejuízo"`) e intensificadores
  (`"forte alta"`, `"leve queda"`);
* termos ambíguos saíram do léxico e viraram frases em `rules.PHRASE_POLARITY`.
  O caso que estava errado: `"juros"` era negativo, então
  `"juros sobre capital próprio"` — uma notícia de provento — pontuava negativo.

---

## LLM externa (opcional, desligada por padrão)

```
LlmProvider
├── AnthropicProvider
├── OpenAiProvider
├── GeminiProvider
└── NullProvider        usado quando desligada ou mal configurada
```

Configuração **exclusivamente por variável de ambiente**. Nenhuma credencial no
código, em log ou no frontend. O `.env.example` traz apenas os nomes.

```env
LLM_ENABLED=false
LLM_PROVIDER=          # anthropic | openai | gemini
LLM_MODEL=
LLM_API_KEY=
LLM_BASE_URL=
LLM_TIMEOUT_SECONDS=
LLM_MAX_RETRIES=
LLM_LANGUAGES=
```

Determinismo: temperatura `0`, `top_p 1` quando o fornecedor aceita, e resposta
em JSON estrito validada antes de ser salva. Texto fora do JSON é extraído ou
rejeitado. Raciocínio longo é truncado — a explicação final é uma justificativa
curta e verificável, não cadeia de pensamento.

**Falhas tratadas:** timeout, limite de requisições, JSON inválido, provedor
indisponível, resposta incompleta, erro de autenticação, texto grande demais,
idioma não identificado. Em qualquer uma delas o motor local do mesmo idioma
assume, o resultado grava `llm_used=false` e `fallback_reason=<motivo>`, e o
relatório diz explicitamente que veio do motor local. **Nenhuma tarefa fica
presa em `pending`.**

---

## Sobre notícias duplicadas

> O sistema identifica cada análise pela combinação da **notícia**, do **ativo**
> e da **versão do motor**. Quando a mesma solicitação é enviada novamente, o
> resultado existente é reutilizado. Se a análise ainda estiver sendo
> processada, a API retorna o mesmo identificador, evitando tarefas duplicadas.
> Notícias apenas semelhantes, mas com conteúdo ou origem diferentes, continuam
> sendo analisadas separadamente.

A deduplicação é responsabilidade da **API e do banco de dados**, não da IA. O
modelo de linguagem não filtra duplicatas — ele nem chega a ser chamado quando
já existe resultado.

Como isso é garantido, tecnicamente:

* `UniqueConstraint(article, ticker, model_version)` na tabela `analises`
  (`uq_analise_art_tic_ver`). Duas requisições simultâneas não criam dois
  registros: a segunda recebe `IntegrityError` e passa a ler a linha vencedora.
* `get_or_create` transacional em `services.request_analysis`.
* Uma linha `pending` que já foi publicada (`queued_at` preenchido) **não** é
  publicada de novo. Só volta para a fila se for `failed` ou se a publicação
  anterior tiver falhado.
* `news_fingerprint` — SHA-256 de título normalizado + resumo normalizado + URL
  canônica + fonte. A URL canônica descarta `utm_*`, `gclid`, `oc`, `ved` e
  outros parâmetros de rastreamento. A mesma matéria coletada com URLs
  diferentes reaproveita o resultado já concluído, sem reprocessar e sem chamar
  a LLM.
* A versão lógica do motor inclui provedor, modelo e versão do prompt (via
  digest curto). Trocar qualquer um deles gera uma chave nova — e portanto uma
  análise nova — em vez de reaproveitar um resultado produzido por outra coisa.

---

## Relatório

Cada resultado responde quatro perguntas, em português e **fundamentado na
própria notícia**:

1. positiva, negativa ou neutra?
2. qual a nota?
3. qual a relevância para o ativo?
4. quais elementos do título ou do resumo justificam o resultado?

Exemplo real gerado pelo motor local:

```
A noticia foi classificada como positiva para PETR4 (Petrobras), com nota +0,46
numa escala de -1 a +1. O resultado foi influenciado por "juros sobre capital
próprio", presentes no titulo. A relevancia para o ativo foi considerada alta
(0.72) porque nome da empresa citado; vocabulario da empresa presente; tema
relevante para o setor: dividends. Analise produzida por motor heuristico de
portugues (rules-ptbr-3.0.0).
```

Saída real do motor para o caso que antes estava errado — `"juros"` no léxico
negativo fazia uma notícia de provento pontuar negativo.

Frases genéricas do tipo *"a IA analisou a notícia e determinou o sentimento"*
não são geradas: o texto só cita expressões que realmente aparecem no título ou
no resumo.

O campo `explanation` recebe o mesmo texto do `report`, então o app mobile, que
já lê `explanation`, passa a mostrar o texto fundamentado **sem nenhuma mudança
no cliente**.

---

## Observabilidade

Logs estruturados no formato `evento chave=valor`, no logger
`sentiment_ai.events`:

| Evento | Quando |
|---|---|
| `analysis_published` | pedido foi para a fila (idioma, origem do idioma, motor, versão) |
| `analysis_reused` | resultado concluído reaproveitado |
| `analysis_reused_fingerprint` | matéria repetida em outra URL reaproveitou o resultado |
| `analysis_already_queued` | pendente já enfileirada, não republicada |
| `analysis_publish_failed` | broker indisponível |
| `analysis_started` | worker pegou o pedido (tentativa, motor) |
| `analysis_completed` | concluída (idioma, motor, `llm_used`, `fallback_reason`, duração) |
| `analysis_failed` / `analysis_timeout` | falha, com tentativa final ou não |
| `engine_version_drift` | configuração mudou entre enfileirar e processar |
| `llm_retry` / `llm_fallback` | tentativa e queda para o motor local |

Nunca são registrados: chave de API, token, prompt, corpo completo da resposta
do provedor. Há uma lista de bloqueio explícita em `observability.FORBIDDEN`.

---

## Execução

```bash
docker compose up --build
```

Criar pedidos para notícias já relacionadas a ativos antes da instalação:

```bash
docker compose exec api python manage.py enqueue_sentiment_backfill
```

## Testes

```bash
pytest --ds=sentiment_ai.testsettings -q
```

`sentiment_ai/testsettings.py` isola a suíte do Oracle da FIAP (SQLite, Celery
em modo eager, LLM desligada). Nenhum teste acessa a rede. As migrations de
produção não foram alteradas: as migrations 0003 a 0008 do app `users`
consultam `user_tab_columns`, uma view do dicionário de dados do Oracle, e por
isso os testes apontam o app `users` para `sentiment_ai/test_migrations/users/`,
que cria a mesma tabela final.
