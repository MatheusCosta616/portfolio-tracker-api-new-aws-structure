import logging

from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from portfolios.models import Asset, Portfolio
from .fetchers.yfinance_fetcher import YFinanceFetcher
from .fetchers.google_news_fetcher import GoogleNewsFetcher
from .models import Analysis
from .dto import AnalysisSerializer, LiveNewsArticleSerializer

logger = logging.getLogger(__name__)

_fetcher = YFinanceFetcher()
_google_fetcher = GoogleNewsFetcher()

FALLBACK_TICKERS = ['PETR4', 'VALE3', 'ITUB4', 'BBDC4', 'ABEV3', 'MGLU3', 'WEGE3', 'BTC-USD', 'HGLG11', 'KNRI11']


def _fetch_live(tickers: list[str]) -> list:
    fetch_tickers = tickers or FALLBACK_TICKERS
    seen_urls: set[str] = set()
    all_articles = []

    def _add(articles):
        for a in articles:
            if a.url not in seen_urls:
                seen_urls.add(a.url)
                all_articles.append(a)

    try:
        _add(_fetcher.fetch(fetch_tickers))
    except Exception as exc:
        logger.error('YFinance live fetch error: %s', exc)

    fii_tickers = [t for t in fetch_tickers if GoogleNewsFetcher._is_fii(t)]
    if fii_tickers:
        try:
            _add(_google_fetcher.fetch(fii_tickers))
        except Exception as exc:
            logger.error('GoogleNews live fetch error: %s', exc)

    all_articles.sort(key=lambda a: a.published_at, reverse=True)
    return all_articles


class GlobalNewsListView(APIView):
    """Real-time news for all assets across all user portfolios."""
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        tickers = list(
            Asset.objects.filter(portfolio__user=request.user)
            .values_list('ticker', flat=True)
            .distinct()
        )
        articles = _fetch_live(tickers)
        return Response(LiveNewsArticleSerializer(articles, many=True).data)


class PortfolioNewsListView(APIView):
    """Real-time news for all assets in a specific portfolio."""
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, portfolio_pk):
        try:
            portfolio = Portfolio.objects.get(pk=portfolio_pk, user=request.user)
        except Portfolio.DoesNotExist:
            raise NotFound('Portfolio not found.')

        tickers = list(portfolio.assets.values_list('ticker', flat=True).distinct())
        articles = _fetch_live(tickers)
        return Response(LiveNewsArticleSerializer(articles, many=True).data)


class AnalysisDetailView(generics.RetrieveAPIView):
    """GET: retrieve a single sentiment analysis by ID."""
    serializer_class = AnalysisSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        user_tickers = Asset.objects.filter(
            portfolio__user=user
        ).values_list('ticker', flat=True).distinct()
        return Analysis.objects.filter(ticker__in=user_tickers).select_related('article')
