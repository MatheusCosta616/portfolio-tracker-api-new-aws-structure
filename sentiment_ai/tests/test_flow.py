import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from news.models import Analysis, NewsArticle, NewsSource
from portfolios.models import Asset, Portfolio
from sentiment_ai.services import request_analysis
from sentiment_ai.tasks import process_analysis


class SentimentQueueFlowTests(TransactionTestCase):
    reset_sequences = True

    def test_request_creates_row_and_worker_completes_same_row(self):
        user = get_user_model().objects.create_user(
            email="test@example.com",
            username="test",
            password="test",
        )
        portfolio = Portfolio.objects.create(user=user, name="Carteira")
        asset = Asset.objects.create(
            portfolio=portfolio,
            ticker="PETR4",
            name="Petrobras",
            asset_type=Asset.AssetType.STOCK,
        )
        source = NewsSource.objects.create(name="Yahoo Finance", slug="yfinance")
        article = NewsArticle.objects.create(
            source=source,
            title="Petrobras anuncia lucro recorde e aumento de dividendos",
            summary="A empresa apresentou forte crescimento.",
            url="https://example.com/news/1",
            published_at=timezone.now(),
        )

        with patch("sentiment_ai.tasks.process_analysis.apply_async") as publisher:
            article.tickers.add(asset)

        analysis = Analysis.objects.get()
        self.assertEqual(analysis.status, Analysis.Status.PENDING)
        publisher.assert_called_once_with(
            args=(analysis.pk,),
            queue="sentiment_analysis",
        )

        # A pending row can be republished after a temporary broker failure;
        # the same database row is reused.
        with patch("sentiment_ai.tasks.process_analysis.apply_async") as republisher:
            same_analysis = request_analysis(article.pk, "PETR4")
        self.assertEqual(same_analysis.pk, analysis.pk)
        republisher.assert_called_once_with(
            args=(analysis.pk,),
            queue="sentiment_analysis",
        )

        process_analysis.apply(args=(analysis.pk,), throw=True)
        analysis.refresh_from_db()

        self.assertEqual(analysis.status, Analysis.Status.COMPLETED)
        self.assertEqual(analysis.attempts, 1)
        result = json.loads(analysis.analise)
        self.assertEqual(result["ticker"], "PETR4")
        self.assertEqual(result["sentiment_label"], "positive")
