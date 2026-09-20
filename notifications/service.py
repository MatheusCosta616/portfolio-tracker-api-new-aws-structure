import logging

import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

logger = logging.getLogger(__name__)

_firebase_initialized = False


def _init_firebase():
    global _firebase_initialized
    if not _firebase_initialized:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True


class FCMService:
    """Thin wrapper around Firebase Admin SDK for push notifications."""

    def __init__(self):
        _init_firebase()

    def send(self, token: str, title: str, body: str, data: dict = None) -> tuple[bool, str | None]:
        """
        Send a push notification to a single device token.
        Returns (success: bool, error_message: str | None).
        """
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        try:
            messaging.send(message)
            return True, None
        except messaging.UnregisteredError:
            return False, 'unregistered_token'
        except Exception as exc:
            logger.error('FCM send error: %s', exc)
            return False, str(exc)
