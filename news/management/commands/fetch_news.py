from django.core.management.base import BaseCommand

from news.tasks import fetch_news_for_all_active_sources


class Command(BaseCommand):
    help = 'Fetch news for all active sources and tickers immediately.'

    def handle(self, *args, **options):
        self.stdout.write('Fetching news...')
        fetch_news_for_all_active_sources()
        self.stdout.write(self.style.SUCCESS('Done.'))
