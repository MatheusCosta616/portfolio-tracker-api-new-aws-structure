# Configuração do Ambiente

## Pré-requisitos

- Python 3.8+
- MySQL 8+
- Redis
- Git

## Passo a Passo

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd portifolio-tracker-api
```

### 2. Criar e ativar o ambiente virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` com suas credenciais:

```env
# DJANGO
SECRET_KEY=gere-uma-chave-com-o-comando-abaixo
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# MYSQL
DB_NAME=portifolio_tracker
DB_USER=root
DB_PASSWORD=sua-senha
DB_HOST=localhost
DB_PORT=3306

# REDIS / CELERY
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# FIREBASE (push notifications)
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
```

Para gerar o `SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Criar o banco de dados MySQL

```sql
CREATE DATABASE portifolio_tracker CHARACTER SET utf8mb4;
```

### 6. Rodar as migrations

```bash
python manage.py migrate
```

### 7. Iniciar o Redis

```bash
brew services start redis
```

### 8. Subir o servidor

```bash
python manage.py runserver
```

A API estará disponível em `http://localhost:8000`.

### 9. (Opcional) Subir o Celery Worker e Beat

Em terminais separados:

```bash
# Worker — executa as tarefas
celery -A portifolio_tracker_api worker --loglevel=info

# Beat — agenda as tarefas periódicas
celery -A portifolio_tracker_api beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```
