from django.db import models


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


class NewsSource(models.Model):
    """Registry of news sources/integrations. Add a new row to plug a new hub."""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'news_sources'

    def __str__(self):
        return self.name


class NewsArticle(models.Model):
    source = models.ForeignKey(NewsSource, on_delete=models.SET_NULL, null=True, related_name='articles')
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    url = models.URLField(max_length=500, unique=True)
    thumbnail_url = models.URLField(max_length=500, blank=True)
    published_at = models.DateTimeField()
    tickers = models.ManyToManyField('portfolios.Asset', related_name='news', blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'news_articles'
        ordering = ['-published_at']

    def __str__(self):
        return self.title
