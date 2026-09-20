# Guia de Endpoints

## Mapa de Endpoints Existentes

| Método | Endpoint | Autenticação | Descrição |
|---|---|---|---|
| POST | `/api/auth/register/` | Não | Cadastro de usuário |
| POST | `/api/auth/login/` | Não | Login, retorna JWT |
| POST | `/api/auth/refresh/` | Não | Renova access token |
| GET/PATCH | `/api/auth/me/` | Sim | Perfil do usuário |
| GET/POST | `/api/portfolios/` | Sim | Listar/criar carteiras |
| GET/PATCH/DELETE | `/api/portfolios/{id}/` | Sim | Detalhe da carteira |
| GET/POST | `/api/portfolios/{id}/assets/` | Sim | Listar/adicionar ativos |
| GET/DELETE | `/api/portfolios/{id}/assets/{id}/` | Sim | Detalhe/remover ativo |
| GET | `/api/news/` | Sim | Notícias de todas as carteiras |
| GET | `/api/news/portfolio/{id}/` | Sim | Notícias de uma carteira |
| POST/DELETE | `/api/notifications/device-token/` | Sim | Registrar/desativar token FCM |

`POST /api/portfolios/{id}/analyse` responde `202 Accepted` com `task_id` e
`status: queued`. A busca externa e a criação das análises acontecem no Celery;
consulte `GET /api/portfolios/{id}/analyses` para acompanhar os estados.

---

## Como Criar um Novo Endpoint

Siga sempre essa ordem de arquivos. Nunca pule etapas.

### Passo 1 — Model

Defina o modelo em `seu_app/models.py`:

```python
from django.db import models

class Exemplo(models.Model):
    nome = models.CharField(max_length=255)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'exemplos'
```

Gere e aplique a migration:

```bash
python manage.py makemigrations seu_app
python manage.py migrate
```

### Passo 2 — Serializer

Crie o serializer em `seu_app/serializers.py`:

```python
from rest_framework import serializers
from .models import Exemplo

class ExemploSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exemplo
        fields = ('id', 'nome', 'criado_em')
        read_only_fields = ('id', 'criado_em')
```

Regras:
- Campos que o usuário não deve escrever vão em `read_only_fields`
- Nunca exponha campos sensíveis (senha, tokens internos)
- Se precisar de serializers diferentes para listagem e detalhe, crie dois: `ExemploListSerializer` e `ExemploSerializer`

### Passo 3 — View

Crie a view em `seu_app/views.py`.

Para endpoints simples, use as views genéricas do DRF:

```python
from rest_framework import generics, permissions
from .models import Exemplo
from .serializers import ExemploSerializer

class ExemploListCreateView(generics.ListCreateAPIView):
    serializer_class = ExemploSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # Sempre filtre pelo usuário autenticado
        return Exemplo.objects.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)
```

Classes genéricas disponíveis:

| Classe | Métodos gerados |
|---|---|
| `ListAPIView` | GET (lista) |
| `CreateAPIView` | POST |
| `ListCreateAPIView` | GET + POST |
| `RetrieveAPIView` | GET (detalhe) |
| `UpdateAPIView` | PUT + PATCH |
| `DestroyAPIView` | DELETE |
| `RetrieveUpdateDestroyAPIView` | GET + PUT + PATCH + DELETE |

### Passo 4 — URL

Adicione a rota em `seu_app/urls.py`:

```python
from django.urls import path
from .views import ExemploListCreateView

urlpatterns = [
    path('', ExemploListCreateView.as_view(), name='exemplo-list'),
]
```

Depois registre no `portifolio_tracker_api/urls.py`:

```python
path('api/exemplos/', include('seu_app.urls')),
```

### Passo 5 — Testes

Escreva os testes antes de considerar o endpoint pronto. Veja o guia em [testing.md](testing.md).

---

## Regras Obrigatórias

- Todo endpoint autenticado deve filtrar dados pelo `request.user`. Nunca retorne dados de outros usuários.
- Nunca use `objects.all()` em views autenticadas — sempre filtre pelo usuário.
- Erros de negócio devem retornar `400`. Recurso não encontrado deve retornar `404`. Não autorizado deve retornar `401` ou `403`.
- Campos calculados ou de leitura sempre vão em `read_only_fields` ou como `SerializerMethodField`.
