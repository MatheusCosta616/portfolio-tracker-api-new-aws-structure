from django.conf import settings
from django.db import models


class DeviceToken(models.Model):
    """FCM push notification token per device."""
    class Platform(models.TextChoices):
        ANDROID = 'android', 'Android'
        IOS = 'ios', 'iOS'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'device_tokens'

    def __str__(self):
        return f'{self.user.email} - {self.platform}'


class NotificationLog(models.Model):
    """Tracks every push notification sent."""
    device_token = models.ForeignKey(DeviceToken, on_delete=models.CASCADE, related_name='logs')
    article = models.ForeignKey('news.NewsArticle', on_delete=models.CASCADE, related_name='notification_logs')
    sent_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'notification_logs'
