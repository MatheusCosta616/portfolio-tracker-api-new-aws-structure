# Arquitetura do Projeto

## Visão Geral

O Portifolio Tracker é uma API REST construída em Django + Django REST Framework. O usuário monta uma carteira de investimentos e recebe notícias 24h relacionadas aos seus ativos via push notification.

## Stack

| Componente | Tecnologia |
|---|---|
| API | Django 4.2 + Django REST Framework |
| Banco de dados | MySQL 8 |
| Autenticação | JWT via `djangorestframework-simplejwt` |
| Fila de tarefas | Celery + Redis |
| Push Notification | Firebase Cloud Messaging (FCM) |
| Notícias | yfinance (Yahoo Finance) |

## Estrutura de Apps

```
portifolio-tracker-api/
├── users/           # Autenticação e perfil do usuário
├── portfolios/      # Carteiras e ativos
├── news/            # Artigos de notícias e fetchers externos
├── notifications/   # Tokens FCM e log de push notifications
└── doc/             # Documentação do projeto
```

Cada app é responsável por um domínio isolado. Nunca coloque lógica de um domínio dentro de outro app.

## Modelos e Relacionamentos

```
User
 └── Portfolio (1:N)
      └── Asset (1:N)  ←──────────────┐
                                       │ M:N
NewsSource                             │
 └── NewsArticle (1:N) ───────────────┘
      └── NotificationLog (1:N)
           └── DeviceToken (N:1) → User
```

## Fluxo de Notícias

```
Celery Beat (periódico)
    ↓
fetch_news_for_all_active_sources (news/tasks.py)
    ↓
Para cada NewsSource ativo → get_fetcher(slug) → fetcher.fetch(tickers)
    ↓
Salva NewsArticle no MySQL
    ↓
send_push_for_article.delay(article_id) (notifications/tasks.py)
    ↓
FCMService.send() → Firebase → React Native
```

## Abstração de Fetchers

Toda integração com fonte de notícias segue o contrato de `BaseNewsFetcher`:

```python
# news/fetchers/base.py
class BaseNewsFetcher(ABC):
    source_slug: str = ''

    def fetch(self, tickers: list[str]) -> list[FetchedArticle]:
        ...
```

Para adicionar um novo hub de notícias, basta:
1. Criar uma classe que herda `BaseNewsFetcher`
2. Registrar o slug em `news/fetchers/registry.py`
3. Inserir um `NewsSource` no banco com o mesmo slug

## Autenticação

Todas as rotas (exceto `/api/auth/register/` e `/api/auth/login/`) exigem o header:

```
Authorization: Bearer <access_token>
```

O token expira em 1 hora. Use `/api/auth/refresh/` com o `refresh_token` para renovar.
