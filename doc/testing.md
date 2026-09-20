# Testes

O projeto usa **pytest** com **pytest-django**. Todo endpoint novo deve ter testes antes de ser considerado pronto.

## Rodando os Testes

```bash
# Todos os testes
pytest -v

# App específico
pytest users/ -v
pytest portfolios/ -v

# Teste específico
pytest users/tests.py::TestLogin::test_login_success -v

# Com relatório de cobertura (instale coverage antes)
pytest --cov=. -v
```

---

## Estrutura de um Teste

Os testes ficam em `tests.py` dentro de cada app. Usamos classes para agrupar testes por funcionalidade.

```python
import pytest
from django.urls import reverse

@pytest.mark.django_db
class TestNomeDaFuncionalidade:
    def test_caso_de_sucesso(self, auth_client):
        url = reverse('nome-da-url')
        response = auth_client.post(url, {'campo': 'valor'})
        assert response.status_code == 201
        assert response.data['campo'] == 'valor'

    def test_caso_de_erro(self, auth_client):
        url = reverse('nome-da-url')
        response = auth_client.post(url, {})
        assert response.status_code == 400
```

### Decorators obrigatórios

- `@pytest.mark.django_db` — obrigatório em toda classe ou função que acessa o banco

---

## Fixtures Globais

Definidas em `conftest.py` na raiz do projeto. Disponíveis em todos os testes.

| Fixture | O que é |
|---|---|
| `api_client` | `APIClient` sem autenticação, formato JSON |
| `user` | Usuário de teste (`test@example.com`) |
| `other_user` | Segundo usuário para testes de isolamento |
| `auth_client` | `APIClient` já autenticado como `user` |

```python
# Uso
def test_meu_endpoint(self, auth_client, user):
    ...

def test_sem_autenticacao(self, api_client):
    ...
```

### Criando fixtures locais

Fixtures específicas de um app ficam no próprio `tests.py`:

```python
@pytest.fixture
def portfolio(db, user):
    from portfolios.models import Portfolio
    return Portfolio.objects.create(user=user, name='Carteira Teste')
```

---

## O Que Testar em Todo Endpoint

Para cada endpoint novo, cubra no mínimo:

### Endpoints de listagem (GET)
- Retorna 200 com dados do usuário autenticado
- Não retorna dados de outros usuários
- Retorna 401 sem autenticação

### Endpoints de criação (POST)
- Retorna 201 com dados criados
- Retorna 400 com payload inválido ou incompleto
- Retorna 401 sem autenticação

### Endpoints de detalhe (GET /{id}/)
- Retorna 200 para recurso do próprio usuário
- Retorna 404 para recurso de outro usuário (nunca 403)
- Retorna 401 sem autenticação

### Endpoints de atualização (PATCH)
- Retorna 200 com dados atualizados
- Retorna 404 para recurso de outro usuário
- Retorna 401 sem autenticação

### Endpoints de exclusão (DELETE)
- Retorna 204 e confirma que o objeto foi removido do banco
- Retorna 404 para recurso de outro usuário
- Retorna 401 sem autenticação

---

## Exemplo Completo

```python
import pytest
from django.urls import reverse
from portfolios.models import Portfolio

@pytest.fixture
def portfolio(db, user):
    return Portfolio.objects.create(user=user, name='Minha Carteira')

@pytest.mark.django_db
class TestPortfolioDetail:
    def test_get_retorna_200(self, auth_client, portfolio):
        url = reverse('portfolio-detail', kwargs={'pk': portfolio.pk})
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.data['name'] == 'Minha Carteira'

    def test_nao_acessa_portfolio_de_outro_usuario(self, auth_client, other_user, db):
        outro = Portfolio.objects.create(user=other_user, name='Alheia')
        url = reverse('portfolio-detail', kwargs={'pk': outro.pk})
        response = auth_client.get(url)
        assert response.status_code == 404

    def test_sem_autenticacao_retorna_401(self, api_client, portfolio):
        url = reverse('portfolio-detail', kwargs={'pk': portfolio.pk})
        response = api_client.get(url)
        assert response.status_code == 401

    def test_delete_remove_do_banco(self, auth_client, portfolio):
        url = reverse('portfolio-detail', kwargs={'pk': portfolio.pk})
        response = auth_client.delete(url)
        assert response.status_code == 204
        assert not Portfolio.objects.filter(pk=portfolio.pk).exists()
```

---

## Regras

- Nunca use `objects.all()` nos testes — crie apenas os dados necessários para cada caso
- Cada teste deve ser independente — a ordem de execução não pode importar
- Nomes de teste devem descrever o comportamento esperado: `test_retorna_404_para_portfolio_inexistente`
- Não teste o Django ou o DRF — teste o comportamento da sua view
