# Portfolio Tracker API

API REST para gerenciamento de carteiras de investimentos com análise de sentimentos em notícias financeiras e notificações push em tempo real.

---

## Sumário

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Stack Tecnológica](#stack-tecnológica)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Pré-requisitos](#pré-requisitos)
- [Configuração do Ambiente](#configuração-do-ambiente)
- [Executando a Aplicação](#executando-a-aplicação)
- [Documentação da API (Swagger)](#documentação-da-api-swagger)
- [Endpoints](#endpoints)
  - [Autenticação](#autenticação)
  - [Carteiras](#carteiras)
  - [Ativos](#ativos)
  - [Análise de Sentimentos](#análise-de-sentimentos)
  - [Notícias](#notícias)
  - [Notificações Push](#notificações-push)
- [Autenticação com Keycloak](#autenticação-com-keycloak)
- [Banco de Dados](#banco-de-dados)
- [Tarefas Assíncronas (Celery)](#tarefas-assíncronas-celery)
- [IA de Sentimentos](#ia-de-sentimentos)
- [Integração de Notícias](#integração-de-notícias)
- [Notificações Push (Firebase)](#notificações-push-firebase)
- [Testes](#testes)
- [Variáveis de Ambiente](#variáveis-de-ambiente)

---

## Visão Geral

O Portfolio Tracker é um sistema backend que permite ao usuário:

- **Gerenciar carteiras de investimentos** com múltiplos ativos (ações, FIIs, ETFs, BDRs e criptomoedas)
- **Receber notícias em tempo real** relacionadas aos tickers da sua carteira via Yahoo Finance
- **Solicitar análise de sentimentos** de notícias para tomar decisões de investimento mais informadas
- **Receber notificações push** no celular quando uma nova notícia relevante for publicada

O backend é completamente desacoplado de autenticação — toda identidade é gerenciada pelo **Keycloak**, e os tokens JWT emitidos por ele são validados pela API via JWKS.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Cliente (App Mobile)                        │
└──────────────────┬────────────────────────────┬─────────────────────┘
                   │ Bearer JWT                  │ Push Notification
                   ▼                             ▼
┌──────────────────────────┐         ┌───────────────────────┐
│     Keycloak : 8080      │         │   Firebase (FCM)       │
│  (Identity Provider)     │         │  (Push Notifications)  │
└──────────────────────────┘         └───────────────────────┘
                   │ valida JWT (JWKS)
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Django REST API : 8000                           │
│                                                                     │
│   users/      portfolios/      news/       notifications/           │
│   controller  controller       controller  controller               │
│   service     dto              dto         service (FCM)            │
│   dto         models           models      dto                      │
│   models                       fetchers/   models                   │
│                                (yfinance)                           │
└────────────────────────────┬────────────────────────────────────────┘
                             │ publica tasks
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      RabbitMQ : 5672                                │
│                  (Message Broker / Fila)                            │
└──────────┬──────────────────────────────────┬───────────────────────┘
           │ fila padrão                       │ fila sentiment_analysis
           ▼                                   ▼
┌─────────────────────┐             ┌──────────────────────────────┐
│   Celery Worker     │             │     Sentiment Worker          │
│   (news tasks +     │             │  (sentiment_ai — modelo de   │
│    push tasks)      │             │   linguagem para análise)    │
└─────────────────────┘             └──────────────────────────────┘
           │                                   │
           └──────────────┬────────────────────┘
                          ▼
              ┌─────────────────────┐
              │   Oracle Database   │
              │  oracle.fiap.com.br │
              └─────────────────────┘
```

### Fluxo principal de análise de sentimentos

```
POST /api/portfolios/{id}/analyse
        │
        ├─ busca tickers da carteira
        ├─ enfileira portfolios.tasks.analyse_portfolio
        ├─ task chama YFinanceFetcher.fetch(tickers) e salva NewsArticle
        ├─ task chama sentiment_ai.services.request_analysis()
        │        └─ cria Analysis(status=PENDING) e publica na fila
        │
        ▼
    A API responde 202 + task_id imediatamente
      └─ cliente consulta GET /api/portfolios/{id}/analyses

    Sentiment Worker consome a fila
        ├─ processa o artigo com o modelo de LM
        ├─ atualiza Analysis(status=COMPLETED, analise=JSON)
        └─ retorna resultado via GET /api/portfolios/{id}/analyses
```

---

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Framework web | Django 4.2 + Django REST Framework 3.15 |
| Autenticação | Keycloak 24 (OpenID Connect / JWT RS256) |
| Banco de dados | Oracle Database (via `oracledb`) |
| Message Broker | RabbitMQ 3.13 |
| Tarefas assíncronas | Celery 5 + Celery Beat |
| Coleta de notícias | yfinance |
| IA de sentimentos | Modelo customizado (`sentiment_ai`) |
| Push Notifications | Firebase Admin SDK (FCM) |
| Documentação | drf-spectacular (OpenAPI 3.0 / Swagger UI) |
| Containerização | Docker + Docker Compose |
| Servidor WSGI | Gunicorn |

---

## Estrutura do Projeto

O projeto segue uma organização inspirada no **padrão MVC do Java/Spring Boot**, onde cada app Django é um módulo de domínio com camadas bem definidas.

```
portifolio-tracker-api/
│
├── portifolio_tracker_api/       # Configuração central (≈ application.properties)
│   ├── settings.py               # Todas as configurações Django
│   ├── urls.py                   # Roteamento raiz + rotas Swagger
│   ├── celery.py                 # Configuração do Celery
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                         # Módulo de infraestrutura transversal
│   └── security.py               # KeycloakAuthentication (≈ Spring Security)
│
├── users/                        # Domínio: Usuários e autenticação
│   ├── models.py                 # Entidade User (@Entity)
│   ├── controller.py             # RegisterView, LoginView, MeView (@RestController)
│   ├── dto.py                    # UserSerializer, RegisterSerializer (DTOs)
│   ├── service.py                # KeycloakService (@Service)
│   └── urls.py
│
├── portfolios/                   # Domínio: Carteiras e Ativos
│   ├── models.py                 # Portfolio, Asset (@Entity)
│   ├── controller.py             # Views de carteiras e ativos (@RestController)
│   ├── dto.py                    # Serializers de carteira/ativo (DTOs)
│   └── urls.py
│
├── news/                         # Domínio: Notícias e Análises
│   ├── models.py                 # NewsSource, NewsArticle, Analysis (@Entity)
│   ├── controller.py             # Views de notícias e análises (@RestController)
│   ├── dto.py                    # AnalysisSerializer, LiveNewsArticleSerializer (DTOs)
│   ├── tasks.py                  # Tasks Celery de busca de notícias
│   ├── fetchers/                 # Camada de acesso a dados externos (≈ @Repository)
│   │   ├── base.py               # BaseNewsFetcher (interface abstrata)
│   │   ├── registry.py           # FETCHER_REGISTRY (registro de integrações)
│   │   └── yfinance_fetcher.py   # Integração com Yahoo Finance
│   └── urls.py
│
├── notifications/                # Domínio: Notificações Push
│   ├── models.py                 # DeviceToken, NotificationLog (@Entity)
│   ├── controller.py             # DeviceTokenView (@RestController)
│   ├── dto.py                    # DeviceTokenSerializer (DTO)
│   ├── service.py                # FCMService (@Service)
│   ├── tasks.py                  # Task Celery de envio de push
│   └── urls.py
│
├── sentiment_ai/                 # Módulo externo — worker de IA de sentimentos
│   └── (não modificar)
│
├── portifolio-tracker-app/       # App mobile React Native (externo)
│   └── (não modificar)
│
├── keycloak/
│   └── portfolio-realm.json      # Configuração do realm importada automaticamente
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── manage.py
├── conftest.py                   # Fixtures globais de teste (pytest)
└── pytest.ini
```

### Mapeamento MVC Java → Python

| Java/Spring | Este projeto |
|---|---|
| `@RestController` | `controller.py` |
| `@Service` | `service.py` |
| `@Repository` | `fetchers/` (news) |
| DTO / Record | `dto.py` |
| `@Entity` / `@Table` | `models.py` |
| Spring Security | `core/security.py` |
| `application.properties` | `portifolio_tracker_api/settings.py` |

---

## Pré-requisitos

- **Docker** >= 24.0 e **Docker Compose** >= 2.0
- Acesso ao banco Oracle em `oracle.fiap.com.br:1521` (credenciais do seu RM)
- *(Opcional)* Python 3.11+ para desenvolvimento local sem Docker

---

## Configuração do Ambiente

### 1. Clone o repositório

```bash
git clone <url-do-repositório>
cd portifolio-tracker-api
```

### 2. Crie o arquivo `.env`

Copie o exemplo e preencha com as suas credenciais:

```bash
cp .env.example .env
```

Edite o `.env` com as variáveis corretas (veja a seção [Variáveis de Ambiente](#variáveis-de-ambiente)).

### 3. (Opcional) Firebase — Notificações Push

Se quiser habilitar push notifications, coloque o arquivo de credenciais do Firebase no diretório raiz com o nome definido em `FIREBASE_CREDENTIALS_PATH` (padrão: `firebase-credentials.json`).

Caso não tenha Firebase, as notificações simplesmente não serão enviadas — o restante da API funciona normalmente.

---

## Executando a Aplicação

### Subir todos os serviços

```bash
docker compose up --build
```

O Docker Compose sobe os seguintes containers na ordem correta (respeitando `healthcheck`):

| Container | Porta | Descrição |
|---|---|---|
| `portfolio_keycloak` | 8080 | Servidor Keycloak com realm importado automaticamente |
| `portfolio_rabbitmq` | 5672 / 15672 | Message broker (15672 = painel de gerenciamento) |
| `portfolio_api` | 8000 | API Django + Gunicorn |
| `portfolio_celery_worker` | — | Worker Celery para notícias e push |
| `portfolio_sentiment_worker` | — | Worker Celery para análise de sentimentos (fila isolada) |
| `portfolio_celery_beat` | — | Agendador de tarefas periódicas |

### Aguardar inicialização

O Keycloak demora cerca de **60 segundos** para inicializar. A API só sobe após o Keycloak e o RabbitMQ estarem saudáveis.

Acompanhe os logs:

```bash
docker compose logs -f api
```

### Verificar saúde dos serviços

```bash
# API Django
curl http://localhost:8000/api/docs/

# Keycloak
curl http://localhost:8080/realms/portfolio

# Painel RabbitMQ (usuário: portfolio / senha: portfolio123)
open http://localhost:15672
```

### Parar os serviços

```bash
docker compose down
```

Para parar e remover volumes (resetar estado do Keycloak e RabbitMQ):

```bash
docker compose down -v
```

### Rodar apenas a API (sem Docker)

```bash
# Instalar dependências
pip install -r requirements.txt

# Aplicar migrations
python manage.py migrate

# Subir servidor de desenvolvimento
python manage.py runserver
```

> **Atenção:** rodando localmente, você ainda precisa do Keycloak e RabbitMQ disponíveis. Você pode subir só eles via `docker compose up keycloak rabbitmq`.

---

## Documentação da API (Swagger)

Com a aplicação rodando, acesse:

| Interface | URL | Descrição |
|---|---|---|
| **Swagger UI** | http://localhost:8000/api/docs/ | Interface interativa para testar endpoints |
| **Redoc** | http://localhost:8000/api/redoc/ | Documentação alternativa, mais legível |
| **Schema OpenAPI** | http://localhost:8000/api/schema/ | Arquivo YAML para importar no Postman/Insomnia |

### Como autenticar no Swagger UI

1. Faça login via `POST /api/auth/login` e copie o `access` token
2. Clique no botão **Authorize** (cadeado) no topo da página
3. Cole o token no formato `Bearer <token>`
4. Clique em **Authorize** — o token fica salvo na sessão

---

## Endpoints

Todos os endpoints protegidos exigem o header:

```
Authorization: Bearer <access_token>
```

### Autenticação

#### `POST /api/auth/register`

Cria um novo usuário no Keycloak.

**Público** (não requer token)

**Body:**
```json
{
  "email": "usuario@exemplo.com",
  "username": "meuusuario",
  "password": "minhasenha123",
  "cpf": "123.456.789-00"
}
```

**Resposta `201`:**
```json
{
  "email": "usuario@exemplo.com",
  "username": "meuusuario"
}
```

**Erros:**
- `400` — E-mail já cadastrado ou dados inválidos
- `503` — Keycloak indisponível

---

#### `POST /api/auth/login`

Autentica o usuário e retorna os tokens JWT do Keycloak.

**Público** (não requer token)

**Body:**
```json
{
  "email": "usuario@exemplo.com",
  "password": "minhasenha123"
}
```

**Resposta `200`:**
```json
{
  "access": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Erros:**
- `400` — Email ou senha ausentes
- `401` — Credenciais inválidas
- `503` — Keycloak indisponível

---

#### `GET /api/auth/me`

Retorna os dados do usuário autenticado.

**Resposta `200`:**
```json
{
  "id": 1,
  "email": "usuario@exemplo.com",
  "username": "meuusuario",
  "cpf": "123.456.789-00"
}
```

---

#### `PATCH /api/auth/me`

Atualiza os dados do usuário autenticado.

**Body (parcial):**
```json
{
  "username": "novonome",
  "cpf": "000.000.000-00"
}
```

---

### Carteiras

#### `GET /api/portfolios/`

Lista todas as carteiras do usuário autenticado.

**Resposta `200`:**
```json
[
  {
    "id": 1,
    "name": "Minha Carteira",
    "asset_count": 3,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z"
  }
]
```

---

#### `POST /api/portfolios/`

Cria uma nova carteira.

**Body:**
```json
{
  "name": "Minha Carteira de FIIs"
}
```

**Resposta `201`:**
```json
{
  "id": 2,
  "name": "Minha Carteira de FIIs",
  "asset_count": 0,
  "assets": [],
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

---

#### `GET /api/portfolios/{id}`

Retorna detalhes de uma carteira, incluindo lista completa de ativos.

**Resposta `200`:**
```json
{
  "id": 1,
  "name": "Minha Carteira",
  "asset_count": 2,
  "assets": [
    {
      "id": 1,
      "ticker": "PETR4",
      "name": "Petrobras",
      "asset_type": "stock",
      "created_at": "2024-01-15T10:00:00Z"
    },
    {
      "id": 2,
      "ticker": "HGLG11",
      "name": "CSHG Logística",
      "asset_type": "fii",
      "created_at": "2024-01-15T11:00:00Z"
    }
  ],
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

---

#### `PATCH /api/portfolios/{id}`

Atualiza o nome da carteira.

**Body:**
```json
{
  "name": "Novo Nome"
}
```

---

#### `DELETE /api/portfolios/{id}`

Remove a carteira e todos os seus ativos. Retorna `204`.

---

### Ativos

#### `GET /api/portfolios/{portfolio_id}/assets`

Lista os ativos de uma carteira.

**Resposta `200`:**
```json
[
  {
    "id": 1,
    "ticker": "PETR4",
    "name": "Petrobras",
    "asset_type": "stock",
    "created_at": "2024-01-15T10:00:00Z"
  }
]
```

---

#### `POST /api/portfolios/{portfolio_id}/assets`

Adiciona um ativo à carteira.

**Body:**
```json
{
  "ticker": "VALE3",
  "name": "Vale S.A.",
  "asset_type": "stock"
}
```

**Tipos de ativo disponíveis (`asset_type`):**

| Valor | Descrição |
|---|---|
| `stock` | Ação (B3 ou NYSE) |
| `fii` | Fundo de Investimento Imobiliário |
| `etf` | ETF |
| `bdr` | Brazilian Depositary Receipt |
| `crypto` | Criptomoeda (ex: `BTC-USD`) |

**Resposta `201`:**
```json
{
  "id": 3,
  "ticker": "VALE3",
  "name": "Vale S.A.",
  "asset_type": "stock",
  "created_at": "2024-01-15T12:00:00Z"
}
```

**Erros:**
- `400` — Ticker já existe na carteira
- `404` — Carteira não encontrada

---

#### `GET /api/portfolios/{portfolio_id}/assets/{asset_id}`

Retorna detalhes de um ativo específico.

---

#### `DELETE /api/portfolios/{portfolio_id}/assets/{asset_id}`

Remove um ativo da carteira. Retorna `204`.

---

### Análise de Sentimentos

#### `POST /api/portfolios/{portfolio_id}/analyse`

Busca as notícias mais recentes para todos os tickers da carteira via Yahoo Finance, salva no banco e enfileira análise de sentimentos para cada artigo.

**Resposta `202`:**
```json
{
  "articles_queued": 5,
  "analyses": [
    {
      "id": 10,
      "ticker": "PETR4",
      "status": "completed",
      "result": {
        "sentimento": "positivo",
        "confianca": 0.87,
        "resumo": "Petrobras anuncia aumento de dividendos..."
      },
      "model_version": "rules-v2.0.0",
      "attempts": 1,
      "started_at": "2024-01-15T10:05:00Z",
      "finished_at": "2024-01-15T10:05:03Z",
      "created_at": "2024-01-15T10:00:00Z",
      "updated_at": "2024-01-15T10:05:03Z",
      "article_title": "Petrobras eleva previsão de dividendos para 2024",
      "article_url": "https://finance.yahoo.com/..."
    }
  ]
}
```

**Campos de `status`:**

| Valor | Descrição |
|---|---|
| `pending` | Na fila, aguardando processamento |
| `processing` | Sendo processado pelo worker |
| `completed` | Análise concluída com resultado em `result` |
| `failed` | Falhou após 3 tentativas |

**Erros:**
- `400` — Carteira sem ativos
- `404` — Carteira não encontrada

---

#### `GET /api/portfolios/{portfolio_id}/analyses`

Lista todas as análises de sentimentos dos tickers da carteira, ordenadas por data de criação (mais recente primeiro).

**Resposta `200`:** lista de objetos `Analysis` (mesmo schema acima).

---

#### `GET /api/news/analyses/{analysis_id}`

Retorna uma análise específica por ID.

---

### Notícias

#### `GET /api/news/`

Retorna notícias em tempo real para **todos os tickers** de todas as carteiras do usuário. Se o usuário não tiver ativos, retorna notícias de um conjunto padrão de tickers do mercado brasileiro.

**Resposta `200`:**
```json
[
  {
    "id": 123456789,
    "title": "Petrobras sobe 3% após anúncio de dividendos",
    "summary": "A empresa divulgou hoje...",
    "url": "https://finance.yahoo.com/...",
    "thumbnail_url": "https://s.yimg.com/...",
    "published_at": "2024-01-15T09:30:00Z",
    "source": {
      "id": 1,
      "name": "Yahoo Finance",
      "slug": "yfinance"
    },
    "tickers": ["PETR4", "PETR3"]
  }
]
```

> As notícias são buscadas **ao vivo** (sem cache) a cada requisição.

---

#### `GET /api/news/portfolio/{portfolio_id}`

Retorna notícias em tempo real apenas para os tickers de uma carteira específica.

**Resposta `200`:** mesmo schema do endpoint de notícias globais.

---

### Notificações Push

#### `POST /api/notifications/device-token`

Registra ou reativa um token de dispositivo para receber notificações push via FCM.

**Body:**
```json
{
  "token": "fXm2...",
  "platform": "android"
}
```

**Plataformas disponíveis:** `android` ou `ios`

**Resposta `201`** (novo token) ou **`200`** (token reativado):
```json
{
  "id": 1,
  "token": "fXm2...",
  "platform": "android",
  "is_active": true,
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

#### `DELETE /api/notifications/device-token`

Desativa um token de dispositivo (logout das notificações push).

**Body:**
```json
{
  "token": "fXm2..."
}
```

**Resposta `204`** em caso de sucesso.

---

## Autenticação com Keycloak

### Como funciona

1. O cliente faz `POST /api/auth/login` com email e senha
2. A API proxia a requisição para o Keycloak (`/realms/portfolio/protocol/openid-connect/token`)
3. O Keycloak retorna um **access token JWT** assinado com RS256
4. O cliente envia o access token em todas as requisições no header `Authorization: Bearer <token>`
5. `core/security.py` (`KeycloakAuthentication`) valida o token via **JWKS** — busca a chave pública diretamente do Keycloak, sem segredo compartilhado

### Configuração do Realm

O arquivo `keycloak/portfolio-realm.json` é importado automaticamente quando o container do Keycloak sobe. Ele configura:

- **Realm:** `portfolio`
- **Client ID:** `portfolio-api` (public client com Direct Access Grants habilitado)
- **Login via email** habilitado
- **Audience mapper** que inclui `portfolio-api` no token (necessário para validação pela API)

### Refresh do token

O endpoint `POST /api/auth/login` retorna também um `refresh` token. Para renovar o access token sem relogar, envie diretamente ao Keycloak:

```bash
curl -X POST http://localhost:8080/realms/portfolio/protocol/openid-connect/token \
  -d "grant_type=refresh_token" \
  -d "client_id=portfolio-api" \
  -d "refresh_token=<refresh_token>"
```

---

## Banco de Dados

O projeto usa **Oracle Database** via `oracledb` (substituto moderno do `cx_Oracle`).

### Modelos e tabelas

| Modelo | Tabela | App | Descrição |
|---|---|---|---|
| `User` | `users` | `users` | Usuário do sistema (estende AbstractUser) |
| `Portfolio` | `portfolios` | `portfolios` | Carteira de investimentos |
| `Asset` | `assets` | `portfolios` | Ativo dentro de uma carteira |
| `NewsSource` | `news_sources` | `news` | Registro de fontes de notícias |
| `NewsArticle` | `news_articles` | `news` | Artigo de notícia salvo |
| `Analysis` | `analises` | `news` | Resultado da análise de sentimentos |
| `DeviceToken` | `device_tokens` | `notifications` | Token FCM do dispositivo |
| `NotificationLog` | `notification_logs` | `notifications` | Log de notificações enviadas |

### Aplicar migrations

```bash
# Com Docker (após o compose up, roda automaticamente)
docker exec portfolio_api python manage.py migrate

# Local
python manage.py migrate
```

### Criar nova migration

```bash
python manage.py makemigrations <nome_do_app>
```

---

## Tarefas Assíncronas (Celery)

O projeto usa **Celery** com **RabbitMQ** como broker.

### Workers

| Container | Fila | Responsabilidade |
|---|---|---|
| `celery-worker` | `default` | Busca de notícias + envio de push |
| `sentiment-worker` | `sentiment_analysis` | Análise de sentimentos (concorrência 1, prefetch 1) |
| `celery-beat` | — | Agendador de tarefas periódicas |

### Tarefas disponíveis

#### `news.tasks.fetch_news_for_ticker(ticker: str)`

Busca e salva notícias para um único ticker. Pode ser chamada manualmente ou disparada após a criação de um ativo.

#### `news.tasks.fetch_news_for_all_active_sources()`

Busca notícias de todas as fontes ativas para todos os tickers cadastrados no banco. **Agendada para rodar toda hora** (no minuto 0) via Celery Beat.

#### `notifications.tasks.send_push_for_article(article_id: int)`

Envia notificação push via FCM para todos os usuários que possuem ativos relacionados ao artigo. Chamada automaticamente após salvar um novo artigo.

### Painel de monitoramento

Acesse o painel do RabbitMQ em http://localhost:15672 para monitorar filas, mensagens e workers.

- Usuário: `portfolio`
- Senha: `portfolio123`

---

## IA de Sentimentos

O módulo `sentiment_ai/` é um worker Celery **independente** com `Dockerfile` próprio (`sentiment_ai/Dockerfile`). Ele consome exclusivamente a fila `sentiment_analysis` e processa artigos de notícias para gerar análises de sentimento.

### Fluxo

```
1. portfolios/controller.py chama sentiment_ai.services.request_analysis()
2. A função cria Analysis(status=PENDING) no banco
3. Publica uma mensagem na fila sentiment_analysis
4. O sentiment-worker consome e processa com o modelo de linguagem
5. Atualiza Analysis(status=COMPLETED, analise=<JSON>)
6. Resultado disponível via GET /api/portfolios/{id}/analyses
```

O worker roda com `--concurrency=1 --prefetch-multiplier=1` para evitar sobrecarga de memória no modelo.

---

## Integração de Notícias

### Arquitetura dos Fetchers

O sistema usa um padrão de **registro de fetchers** para permitir adicionar novas fontes de notícias sem modificar o código existente.

```python
# news/fetchers/registry.py
FETCHER_REGISTRY = {
    'yfinance': YFinanceFetcher,
    # 'finnhub': FinnhubFetcher,   # adicione aqui para nova fonte
}
```

### Como adicionar uma nova fonte

1. Crie `news/fetchers/minha_fonte_fetcher.py` estendendo `BaseNewsFetcher`
2. Implemente o método `fetch(tickers: list[str]) -> list[FetchedArticle]`
3. Registre no `FETCHER_REGISTRY` em `registry.py`
4. Crie um `NewsSource` no banco com o mesmo slug

### YFinance Fetcher

O `YFinanceFetcher` adapta automaticamente os tickers brasileiros para o formato aceito pelo Yahoo Finance:

| Ticker cadastrado | Símbolo enviado ao yfinance |
|---|---|
| `PETR4` | `PETR4.SA` |
| `HGLG11` | `HGLG11.SA` |
| `AAPL` | `AAPL` |
| `BTC-USD` | `BTC-USD` |

A lógica de detecção: se o último caractere do ticker for um dígito, é um ticker B3 e recebe `.SA`. Os artigos retornados têm o sufixo `.SA` removido para manter consistência com o que o usuário cadastra.

---

## Notificações Push (Firebase)

### Configuração

1. No [Firebase Console](https://console.firebase.google.com/), crie um projeto e gere uma **Service Account Key** (JSON) em Project Settings > Service Accounts
2. Salve o arquivo com o nome definido em `FIREBASE_CREDENTIALS_PATH` (padrão: `firebase-credentials.json`) na raiz do projeto
3. Configure a variável no `.env`

### Fluxo de envio

1. App mobile registra seu token FCM via `POST /api/notifications/device-token`
2. Quando um novo `NewsArticle` é salvo, a task `send_push_for_article` é enfileirada automaticamente
3. O worker identifica os usuários que possuem ativos relacionados ao artigo
4. Envia a notificação via `FCMService.send()` para cada dispositivo com `is_active=True`
5. Registra o resultado (sucesso/falha) em `NotificationLog`

### Desativar notificações

O app mobile deve chamar `DELETE /api/notifications/device-token` ao fazer logout, passando o token do dispositivo. O token é marcado como `is_active=False` e não recebe mais notificações.

---

## Testes

O projeto usa **pytest** com **pytest-django**.

### Rodar todos os testes

```bash
pytest
```

### Rodar testes de um módulo específico

```bash
pytest users/tests.py
pytest portfolios/tests.py -v
```

### Rodar um teste específico

```bash
pytest portfolios/tests.py::TestAssets::test_create_asset -v
```

### Fixtures disponíveis (`conftest.py`)

| Fixture | Descrição |
|---|---|
| `api_client` | Cliente DRF sem autenticação |
| `auth_client` | Cliente DRF autenticado com `user` |
| `user` | Usuário padrão de teste (`test@example.com`) |
| `other_user` | Segundo usuário para testes de isolamento (`other@example.com`) |

### Cobertura de testes

**Autenticação (`users/tests.py`):**
- Registro com sucesso
- Registro com e-mail duplicado
- Registro com senha fraca (menos de 6 caracteres)
- Login com sucesso
- Login com credenciais inválidas
- Acesso a `/me` autenticado e não autenticado

**Carteiras e Ativos (`portfolios/tests.py`):**
- Listagem de carteiras próprias com isolamento entre usuários
- Criação de carteira com e sem nome
- Detalhe, atualização (`PATCH`) e exclusão de carteira
- Tentativa de acesso a carteira de outro usuário (deve retornar `404`)
- Listagem, criação e exclusão de ativos
- Ticker duplicado na mesma carteira (deve retornar `400`)
- Acesso a ativos de carteira inexistente (deve retornar `404`)

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | — | Chave secreta do Django (obrigatório em produção) |
| `DEBUG` | `False` | Modo debug do Django |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts permitidos (separados por vírgula) |
| `DB_NAME` | `orcl` | Nome/SID do banco Oracle |
| `DB_USER` | — | Usuário do banco Oracle |
| `DB_PASSWORD` | — | Senha do banco Oracle |
| `DB_HOST` | `oracle.fiap.com.br` | Host do banco Oracle |
| `DB_PORT` | `1521` | Porta do banco Oracle |
| `KEYCLOAK_SERVER_URL` | `http://localhost:8080` | URL base do servidor Keycloak |
| `KEYCLOAK_REALM` | `portfolio` | Nome do realm no Keycloak |
| `KEYCLOAK_CLIENT_ID` | `portfolio-api` | Client ID configurado no Keycloak |
| `CELERY_BROKER_URL` | `amqp://guest:guest@localhost:5672/` | URL de conexão ao RabbitMQ |
| `CELERY_RESULT_BACKEND` | `rpc://` | Backend de resultados do Celery |
| `FIREBASE_CREDENTIALS_PATH` | `firebase-credentials.json` | Caminho para o JSON de credenciais do Firebase |
