from django.core.management.base import BaseCommand

from news.models import NewsArticle
from sentiment_ai.services import request_analysis


class Command(BaseCommand):
    help = "Create missing sentiment requests for news/ticker relationships already in the database."

    def handle(self, *args, **options):
        requested = 0
        for article in NewsArticle.objects.prefetch_related("tickers").iterator():
            tickers = {ticker.upper() for ticker in article.tickers.values_list("ticker", flat=True)}
            for ticker in tickers:
                request_analysis(article_id=article.pk, ticker=ticker)
                requested += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {requested} article/ticker relationships."))
