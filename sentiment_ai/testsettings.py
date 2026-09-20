"""Settings de teste do modulo de sentimento.

Isola a suite do Oracle da FIAP: os testes nao devem depender de rede nem de um
schema remoto para rodar. Nada aqui altera os settings de producao.

Uso:
    pytest --ds=sentiment_ai.testsettings -q

O banco de teste e um arquivo, e nao ``:memory:``, porque o teste de
concorrencia abre conexoes em threads diferentes e elas precisam enxergar o
mesmo banco.
"""

from portifolio_tracker_api.settings import *  # noqa: F401,F403

import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.gettempdir()) / "sentiment_ai_test.sqlite3"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_TEST_DB),
        "TEST": {"NAME": str(_TEST_DB)},
        # O teste de concorrencia abre varias conexoes ao mesmo tempo.
        "OPTIONS": {"timeout": 30},
    }
}

# As tasks rodam no processo do teste; nada vai para o RabbitMQ.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# A LLM fica desligada por padrao nos testes; quem precisa dela injeta um
# provedor falso diretamente no motor.
LLM_ENABLED = False
LLM_PROVIDER = ""
LLM_MODEL = ""
LLM_API_KEY = ""

SENTIMENT_FALLBACK_LANGUAGE = "pt-BR"

# As migrations 0003..0008 do app ``users`` consultam o dicionario de dados do
# Oracle (``user_tab_columns``) e nao rodam em nenhum outro backend. Nos testes
# o app aponta para um pacote proprio com a mesma tabela final. As migrations
# de producao ficam intactas.
MIGRATION_MODULES = {"users": "sentiment_ai.test_migrations.users"}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
}
