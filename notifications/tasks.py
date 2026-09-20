import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_push_for_article(article_id: int):
    """
    Sends FCM push notifications to all users who hold an asset
    related to the given news article.
    """
    from news.models import NewsArticle
    from .models import DeviceToken, NotificationLog
    from .service import FCMService

    try:
        article = NewsArticle.objects.prefetch_related('tickers__portfolio__user').get(pk=article_id)
    except NewsArticle.DoesNotExist:
        logger.warning('Article %d not found, skipping push.', article_id)
        return

    user_ids = set(
        article.tickers
        .values_list('portfolio__user_id', flat=True)
        .distinct()
    )

    if not user_ids:
        return

    tokens = DeviceToken.objects.filter(user_id__in=user_ids, is_active=True)
    if not tokens.exists():
        return

    fcm = FCMService()
    for device in tokens:
        success, error = fcm.send(
            token=device.token,
            title=article.title[:100],
            body=article.summary[:200] if article.summary else article.title[:200],
            data={'article_id': str(article.pk), 'url': article.url},
        )
        NotificationLog.objects.create(
            device_token=device,
            article=article,
            success=success,
            error_message=error or '',
        )
        if not success:
            logger.warning('FCM push failed for device %d: %s', device.pk, error)
