# Sentiment AI — worker mínimo

Este diretório transforma a IA de sentimento em um consumidor Celery dedicado.
Ele não cria tabelas próprias: usa a tabela existente `analises` do app `news`.

## Fluxo

1. O código atual associa uma `NewsArticle` a um ou mais `Asset` por meio de `article.tickers.add(...)`.
2. O signal deste diretório cria uma linha em `analises` para cada combinação notícia + ticker.
3. A fila RabbitMQ recebe apenas o ID dessa linha.
4. O worker `sentiment-worker` processa um pedido por vez.
5. O worker altera a mesma linha para `processing` e depois `completed` ou `failed`.
6. O JSON completo do resultado é salvo no campo existente `analise`.

## Mensagem publicada na fila

A task Celery recebe somente o argumento inteiro `analysis_id`. Na prática, a
mensagem representa:

```json
{"analysis_id": 123}
```

## Resultado

O campo `analise` recebe JSON com:

- ticker;
- idioma;
- relevância;
- sentimento textual;
- ajuste setorial;
- impacto final;
- rótulo `positive`, `neutral`, `negative` ou `irrelevant`;
- confiança heurística;
- sinais e tópicos encontrados;
- explicação;
- versão do motor;
- tempo de processamento.

## Execução

Depois das mudanças externas descritas em `INTEGRATION.md`:

```bash
docker compose up --build
```

Para criar pedidos para notícias que já estavam relacionadas a ativos antes da
instalação do módulo:

```bash
docker compose exec api python manage.py enqueue_sentiment_backfill
```
