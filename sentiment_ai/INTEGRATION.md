# Alterações externas mínimas

A integração foi desenhada para não alterar o fluxo de notícias, as views, os
serializers, o mobile ou as tasks existentes. Somente três arquivos existentes
foram editados e uma migration foi adicionada.

## 1. Copiar o diretório

Copie `sentiment_ai/` para a raiz do projeto, ao lado de `news/`, `portfolios/`
e `notifications/`.

## 2. `news/models.py`

Substitua somente a classe `Analysis` pela versão abaixo. As classes
`NewsSource` e `NewsArticle` permanecem como estavam.

```python
class Analysis(models.Model):
    """Sentiment-analysis request and result for one article and ticker."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        PROCESSING = 'processing', 'Processando'
        COMPLETED = 'completed', 'Concluída'
        FAILED = 'failed', 'Falhou'

    article = models.ForeignKey('NewsArticle', on_delete=models.CASCADE, related_name='analyses')
    ticker = models.CharField(max_length=20, blank=True, default='', db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    analise = models.TextField(blank=True, default='')
    model_version = models.CharField(max_length=50, default='rules-v2.0.0')
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analises'
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'Analysis #{self.pk} ({self.ticker or "sem ticker"}) - {self.status}'
```

## 3. Migration

Copie o arquivo entregue em:

```text
news/migrations/0003_analysis_queue_fields.py
```

Ele somente amplia a tabela existente `analises`. Não cria tabelas novas para a
IA e não apaga dados anteriores.

## 4. `portifolio_tracker_api/settings.py`

Adicione uma única linha ao final de `INSTALLED_APPS`:

```python
'sentiment_ai.apps.SentimentAIConfig',
```

Não é necessário alterar as configurações do Celery. A publicação informa a
fila explicitamente.

## 5. `docker-compose.yml`

Adicione o serviço `sentiment-worker` presente no projeto completo. Ele usa:

```text
-Q sentiment_analysis
--concurrency=1
--prefetch-multiplier=1
```

O worker geral existente não precisa ser alterado.

## 6. Aplicar

```bash
docker compose up --build
```

O comando atual da API já executa `python manage.py migrate --fake-initial`,
portanto a nova migration será aplicada na inicialização.

## Arquivos que não foram alterados

- `news/tasks.py`;
- `news/views.py`;
- `news/serializers.py`;
- `portfolios/views.py`;
- `portfolios/serializers.py`;
- aplicativo Expo;
- `requirements.txt` da raiz.

A dependência adicional da IA é instalada somente pelo
`sentiment_ai/Dockerfile`.
