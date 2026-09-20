from django.apps import AppConfig


class SentimentAIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sentiment_ai"
    verbose_name = "Sentiment AI"

    def ready(self):
        # Register the listener that creates an Analysis row whenever a news
        # article is associated with a ticker.
        from . import signals  # noqa: F401
