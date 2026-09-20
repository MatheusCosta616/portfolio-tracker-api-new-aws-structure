from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.urls import reverse

from news.fetchers.base import FetchedArticle
from news.models import Analysis, NewsArticle, NewsSource
from portfolios.models import Asset, Portfolio


def _make_article(ticker: str, title: str = 'Notícia teste') -> FetchedArticle:
    return FetchedArticle(
        title=title,
        url=f'https://example.com/{ticker}',
        published_at=datetime.now(tz=timezone.utc),
        summary='Resumo',
        thumbnail_url='',
        related_tickers=[ticker],
    )


@pytest.fixture
def portfolio(db, user):
    return Portfolio.objects.create(user=user, name='Carteira')


@pytest.fixture
def asset(db, portfolio):
    return Asset.objects.create(
        portfolio=portfolio,
        ticker='PETR4',
        name='Petrobras',
        asset_type=Asset.AssetType.STOCK,
    )


@pytest.fixture
def news_source(db):
    return NewsSource.objects.create(name='Yahoo Finance', slug='yfinance', is_active=True)


@pytest.fixture
def db_article(db, news_source, asset):
    article = NewsArticle.objects.create(
        source=news_source,
        title='Petrobras anuncia dividendos',
        url='https://example.com/news/1',
        published_at=datetime.now(tz=timezone.utc),
    )
    article.tickers.add(asset)
    return article


@pytest.mark.django_db
class TestGlobalNews:
    def test_returns_news_for_user_assets(self, auth_client, asset):
        fake = _make_article('PETR4', 'Petrobras sobe 5%')
        with patch('news.controller._fetch_live', return_value=[fake]):
            response = auth_client.get(reverse('news-global'))
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['title'] == 'Petrobras sobe 5%'
        assert 'PETR4' in response.data[0]['tickers']

    def test_returns_empty_when_fetcher_fails(self, auth_client, asset):
        with patch('news.controller._fetch_live', return_value=[]):
            response = auth_client.get(reverse('news-global'))
        assert response.status_code == 200
        assert response.data == []

    def test_unauthenticated_returns_401(self, api_client):
        response = api_client.get(reverse('news-global'))
        assert response.status_code == 401


@pytest.mark.django_db
class TestPortfolioNews:
    def test_returns_news_for_portfolio(self, auth_client, portfolio, asset):
        fake = _make_article('PETR4', 'Vale bate recorde')
        with patch('news.controller._fetch_live', return_value=[fake]):
            response = auth_client.get(
                reverse('news-portfolio', kwargs={'portfolio_pk': portfolio.pk})
            )
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_nonexistent_portfolio_returns_404(self, auth_client):
        response = auth_client.get(
            reverse('news-portfolio', kwargs={'portfolio_pk': 9999})
        )
        assert response.status_code == 404

    def test_cannot_access_other_users_portfolio_news(self, auth_client, other_user, db):
        other_portfolio = Portfolio.objects.create(user=other_user, name='Alheia')
        response = auth_client.get(
            reverse('news-portfolio', kwargs={'portfolio_pk': other_portfolio.pk})
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestAnalysisDetail:
    def test_returns_analysis_for_user_ticker(self, auth_client, asset, db_article):
        analysis = Analysis.objects.create(
            article=db_article,
            ticker='PETR4',
            status=Analysis.Status.COMPLETED,
            analise='{"sentimento": "positivo"}',
        )
        response = auth_client.get(
            reverse('analysis-detail', kwargs={'pk': analysis.pk})
        )
        assert response.status_code == 200
        assert response.data['ticker'] == 'PETR4'
        assert response.data['status'] == 'completed'

    def test_cannot_access_analysis_for_other_users_ticker(
        self, auth_client, other_user, news_source, db
    ):
        other_portfolio = Portfolio.objects.create(user=other_user, name='Outra')
        other_asset = Asset.objects.create(
            portfolio=other_portfolio, ticker='VALE3', name='Vale', asset_type='stock'
        )
        article = NewsArticle.objects.create(
            source=news_source,
            title='Vale noticia',
            url='https://example.com/vale',
            published_at=datetime.now(tz=timezone.utc),
        )
        analysis = Analysis.objects.create(
            article=article,
            ticker='VALE3',
            status=Analysis.Status.COMPLETED,
        )
        response = auth_client.get(
            reverse('analysis-detail', kwargs={'pk': analysis.pk})
        )
        assert response.status_code == 404
