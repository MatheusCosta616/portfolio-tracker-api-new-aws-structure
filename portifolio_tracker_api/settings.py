from pathlib import Path
import sys
import environ
import oracledb

# oracledb is the modern replacement for cx_Oracle; register it so Django's oracle backend finds it
oracledb.version = "8.3.0"
sys.modules["cx_Oracle"] = oracledb
oracledb.defaults.fetch_lobs = False

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False)
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default='dev-secret-key-change-in-production')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '192.168.15.38'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'django_celery_beat',
    'users',
    'portfolios',
    'news',
    'notifications',
    'sentiment_ai.apps.SentimentAIConfig',
    'drf_spectacular',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'portifolio_tracker_api.urls'

APPEND_SLASH = False

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'portifolio_tracker_api.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.oracle',
        'NAME': env('DB_NAME', default='orcl'),
        'USER': env('DB_USER', default=''),
        'PASSWORD': env('DB_PASSWORD', default=''),
        'HOST': env('DB_HOST', default='oracle.fiap.com.br'),
        'PORT': env('DB_PORT', default='1521'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.User'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    # >>> MUDOU: Keycloak -> Cognito
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.security.CognitoAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Portfolio Tracker API',
    'DESCRIPTION': 'API para gerenciamento de carteiras de investimentos com análise de sentimentos de notícias.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SECURITY': [{'bearerAuth': []}],
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

# >>> MUDOU: bloco do Keycloak substituído pelo do Cognito
COGNITO_REGION = env('COGNITO_REGION', default='us-east-1')
COGNITO_USER_POOL_ID = env('COGNITO_USER_POOL_ID', default='')
COGNITO_APP_CLIENT_ID = env('COGNITO_APP_CLIENT_ID', default='')
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
COGNITO_JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"

CORS_ALLOWED_ORIGINS = [
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://192.168.15.38:8081',
]
CORS_ALLOW_ALL_ORIGINS = True

# >>> MUDOU: RabbitMQ -> SQS
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='sqs://')
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'region': env('COGNITO_REGION', default='us-east-1'),
}
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default=None)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TASK_TIME_LIMIT = 300

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'fetch-news-every-hour': {
        'task': 'news.tasks.fetch_news_for_all_active_sources',
        'schedule': crontab(minute=0),
    },
}

FIREBASE_CREDENTIALS_PATH = env('FIREBASE_CREDENTIALS_PATH', default='firebase-credentials.json')