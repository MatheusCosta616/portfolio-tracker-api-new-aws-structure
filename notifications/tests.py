import pytest
from django.urls import reverse

from .models import DeviceToken


@pytest.mark.django_db
class TestDeviceToken:
    def test_register_token(self, auth_client, user):
        url = reverse('device-token')
        data = {'token': 'fcm-token-abc123', 'platform': 'android'}
        response = auth_client.post(url, data)
        assert response.status_code == 201
        assert DeviceToken.objects.filter(user=user, token='fcm-token-abc123').exists()

    def test_register_same_token_twice_returns_200(self, auth_client, user):
        url = reverse('device-token')
        data = {'token': 'fcm-token-abc123', 'platform': 'android'}
        auth_client.post(url, data)
        response = auth_client.post(url, data)
        assert response.status_code == 200
        assert DeviceToken.objects.filter(token='fcm-token-abc123').count() == 1

    def test_register_token_missing_platform_fails(self, auth_client):
        url = reverse('device-token')
        data = {'token': 'fcm-token-abc123'}
        response = auth_client.post(url, data)
        assert response.status_code == 400

    def test_deactivate_token(self, auth_client, user):
        DeviceToken.objects.create(user=user, token='fcm-token-abc123', platform='android')
        url = reverse('device-token')
        response = auth_client.delete(url, {'token': 'fcm-token-abc123'}, format='json')
        assert response.status_code == 204
        assert not DeviceToken.objects.get(token='fcm-token-abc123').is_active

    def test_deactivate_nonexistent_token_returns_404(self, auth_client):
        url = reverse('device-token')
        response = auth_client.delete(url, {'token': 'nonexistent'}, format='json')
        assert response.status_code == 404

    def test_unauthenticated_returns_401(self, api_client):
        url = reverse('device-token')
        response = api_client.post(url, {'token': 'x', 'platform': 'ios'})
        assert response.status_code == 401
