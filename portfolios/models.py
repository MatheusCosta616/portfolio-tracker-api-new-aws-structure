from django.conf import settings
from django.db import models


class Portfolio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='portfolios')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'portfolios'

    def __str__(self):
        return f'{self.user.email} - {self.name}'


class Asset(models.Model):
    class AssetType(models.TextChoices):
        STOCK = 'stock', 'Ação'
        FII = 'fii', 'FII'
        CRYPTO = 'crypto', 'Cripto'
        ETF = 'etf', 'ETF'
        BDR = 'bdr', 'BDR'

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='assets')
    ticker = models.CharField(max_length=20)
    name = models.CharField(max_length=255, blank=True)
    asset_type = models.CharField(max_length=20, choices=AssetType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assets'
        unique_together = ('portfolio', 'ticker')

    def __str__(self):
        return f'{self.ticker} ({self.get_asset_type_display()})'
