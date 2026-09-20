from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse


def _mock_keycloak_response(status_code: int, ok: bool = True):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = ok
    return resp


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client):
        url = reverse('auth-register')
        data = {'email': 'new@example.com', 'username': 'newuser', 'password': 'strongpass123'}
        with patch('users.controller.KeycloakService.register_user',
                   return_value=_mock_keycloak_response(201)):
            response = api_client.post(url, data)
        assert response.status_code == 201
        assert response.data['email'] == 'new@example.com'
        assert 'password' not in response.data

    def test_register_duplicate_email(self, api_client, user):
        url = reverse('auth-register')
        data = {'email': 'test@example.com', 'username': 'x', 'password': 'strongpass123'}
        with patch('users.controller.KeycloakService.register_user',
                   return_value=_mock_keycloak_response(409, ok=False)):
            response = api_client.post(url, data)
        assert response.status_code == 400

    def test_register_allows_same_username_for_different_emails(self, api_client):
        url = reverse('auth-register')
        first = {'email': 'first@example.com', 'username': 'same-name', 'password': 'strongpass123'}
        second = {'email': 'second@example.com', 'username': 'same-name', 'password': 'strongpass123'}
        with patch('users.controller.KeycloakService.register_user',
                   return_value=_mock_keycloak_response(201)):
            assert api_client.post(url, first).status_code == 201
            assert api_client.post(url, second).status_code == 201

        from django.contrib.auth import get_user_model
        User = get_user_model()
        assert User.objects.filter(username='same-name').count() == 2

    def test_register_uses_email_as_keycloak_username(self, api_client):
        url = reverse('auth-register')
        data = {'email': 'first@example.com', 'username': 'same-name', 'password': 'strongpass123'}
        with patch('users.controller.KeycloakService.register_user',
                   return_value=_mock_keycloak_response(201)) as register_user:
            response = api_client.post(url, data)

        assert response.status_code == 201
        register_user.assert_called_once_with(data)
        payload = register_user.call_args.args[0]
        assert payload['email'] != payload['username']

    def test_register_weak_password(self, api_client):
        url = reverse('auth-register')
        data = {'email': 'new@example.com', 'username': 'x', 'password': '123'}
        # Validation fails before reaching KeycloakService — no mock needed
        response = api_client.post(url, data)
        assert response.status_code == 400

    def test_register_keycloak_unavailable(self, api_client):
        url = reverse('auth-register')
        data = {'email': 'new@example.com', 'username': 'newuser', 'password': 'strongpass123'}
        with patch('users.controller.KeycloakService.register_user',
                   side_effect=Exception('Connection refused')):
            response = api_client.post(url, data)
        assert response.status_code == 503


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client):
        url = reverse('auth-login')
        mock_resp = _mock_keycloak_response(200)
        mock_resp.json.return_value = {'access_token': 'tok', 'refresh_token': 'ref'}
        with patch('users.controller.KeycloakService.login', return_value=mock_resp):
            response = api_client.post(url, {'email': 'test@example.com', 'password': 'strongpass123'})
        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login_wrong_password(self, api_client):
        url = reverse('auth-login')
        with patch('users.controller.KeycloakService.login',
                   return_value=_mock_keycloak_response(401, ok=False)):
            response = api_client.post(url, {'email': 'test@example.com', 'password': 'wrong'})
        assert response.status_code == 401

    def test_login_unknown_email(self, api_client):
        url = reverse('auth-login')
        with patch('users.controller.KeycloakService.login',
                   return_value=_mock_keycloak_response(401, ok=False)):
            response = api_client.post(url, {'email': 'nobody@example.com', 'password': 'pass'})
        assert response.status_code == 401

    def test_login_creates_local_user_for_new_email(self, api_client):
        url = reverse('auth-login')
        mock_resp = _mock_keycloak_response(200)
        mock_resp.json.return_value = {'access_token': 'tok', 'refresh_token': 'ref'}
        with patch('users.controller.KeycloakService.login', return_value=mock_resp):
            response = api_client.post(url, {'email': 'new@example.com', 'password': 'strongpass123'})

        assert response.status_code == 200
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(email='new@example.com')
        assert user.username == 'new@example.com'

    def test_login_missing_fields_returns_400(self, api_client):
        url = reverse('auth-login')
        # LoginView checks for empty fields before calling Keycloak — no mock needed
        response = api_client.post(url, {})
        assert response.status_code == 400

    def test_login_keycloak_unavailable(self, api_client):
        url = reverse('auth-login')
        with patch('users.controller.KeycloakService.login',
                   side_effect=Exception('Connection refused')):
            response = api_client.post(url, {'email': 'x@x.com', 'password': 'pass'})
        assert response.status_code == 503


@pytest.mark.django_db
class TestMe:
    def test_me_authenticated(self, auth_client, user):
        url = reverse('auth-me')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.data['email'] == user.email

    def test_me_unauthenticated(self, api_client):
        url = reverse('auth-me')
        response = api_client.get(url)
        assert response.status_code == 401
