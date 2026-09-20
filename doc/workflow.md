# Rotina de Trabalho

## Antes de Começar

Sempre que for trabalhar no projeto, ative o ambiente virtual:

```bash
source venv/bin/activate
```

Se houver migrations pendentes de outros devs:

```bash
python manage.py migrate
```

---

## Fluxo de uma Tarefa

```
1. Entender o que vai ser feito
2. Criar o model (se necessário) + migration
3. Criar o serializer
4. Criar a view
5. Registrar a URL
6. Escrever os testes
7. Rodar os testes → todos devem passar
8. Testar manualmente no Postman
9. Abrir PR
```

Nunca entregue código sem testes passando.

---

## Convenções de Código

### Nomenclatura

| O que | Convenção | Exemplo |
|---|---|---|
| Models | PascalCase, singular | `Portfolio`, `NewsArticle` |
| Views | PascalCase + sufixo de ação | `PortfolioListCreateView` |
| Serializers | PascalCase + `Serializer` | `PortfolioSerializer` |
| URLs (name) | kebab-case | `portfolio-list`, `asset-detail` |
| Campos de model | snake_case | `created_at`, `asset_type` |
| Arquivos | snake_case | `views.py`, `news_fetcher.py` |

### Estrutura de Apps

Cada app tem responsabilidade única. Antes de criar código, pergunte: "esse código pertence a qual domínio?"

- Lógica de usuário → `users/`
- Lógica de carteira/ativo → `portfolios/`
- Lógica de notícias/fetchers → `news/`
- Lógica de push notification → `notifications/`

Se a lógica pertencer a dois domínios ao mesmo tempo, coloque no app que inicia a ação.

### Segurança

- Nunca faça `objects.all()` em views autenticadas — sempre filtre por `request.user`
- Nunca exponha campos sensíveis em serializers
- Toda view nova deve ter `permission_classes = (permissions.IsAuthenticated,)` por padrão, exceto rotas públicas explícitas

### Migrations

- Uma migration por alteração lógica (não agrupe alterações não relacionadas)
- Nunca edite uma migration já aplicada em produção — crie uma nova
- Sempre rode `makemigrations` antes do `migrate`:

```bash
python manage.py makemigrations nome_do_app
python manage.py migrate
```

---

## Adicionando uma Nova Fonte de Notícias

O projeto foi desenhado para suportar múltiplos hubs de notícias. Para adicionar um novo:

1. Crie o fetcher em `news/fetchers/novo_fetcher.py` herdando `BaseNewsFetcher`
2. Implemente o método `fetch(tickers) -> list[FetchedArticle]`
3. Registre o slug em `news/fetchers/registry.py`
4. Insira um `NewsSource` no banco com `slug` igual ao registrado e `is_active=True`

O sistema vai buscar notícias dessa fonte automaticamente no próximo ciclo do Celery Beat.

---

## Variáveis de Ambiente

Nunca suba o arquivo `.env` para o repositório. Ele está no `.gitignore`.

Se adicionar uma nova variável de ambiente:
1. Adicione no `.env` local
2. Adicione no `.env.example` com um valor de exemplo
3. Leia ela no `settings.py` via `env('NOME_DA_VARIAVEL')`
4. Avise o time para atualizar o `.env` local

---

## Tarefas Assíncronas (Celery)

Tasks ficam no arquivo `tasks.py` de cada app. Para criar uma nova task:

```python
from celery import shared_task

@shared_task
def minha_task(parametro):
    # lógica aqui
    pass
```

Para chamar de forma assíncrona:

```python
minha_task.delay(parametro)
```

Para agendar via Celery Beat, acesse o admin Django em `/admin/` e configure em **Periodic Tasks**.

---

## Comandos do Dia a Dia

```bash
# Rodar o servidor
python manage.py runserver

# Rodar todos os testes
pytest -v

# Rodar testes de um app específico
pytest users/ -v

# Gerar migration
python manage.py makemigrations nome_do_app

# Aplicar migrations
python manage.py migrate

# Acessar shell do Django
python manage.py shell

# Criar superusuário para o admin
python manage.py createsuperuser

# Subir Celery Worker
celery -A portifolio_tracker_api worker --loglevel=info

# Subir Celery Beat
celery -A portifolio_tracker_api beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```
