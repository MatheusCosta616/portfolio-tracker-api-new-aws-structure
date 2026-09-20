import pytest
from django.urls import reverse

from .models import Asset, Portfolio


@pytest.fixture
def portfolio(db, user):
    return Portfolio.objects.create(user=user, name='Minha Carteira')


@pytest.fixture
def asset(db, portfolio):
    return Asset.objects.create(
        portfolio=portfolio,
        ticker='PETR4',
        name='Petrobras',
        asset_type=Asset.AssetType.STOCK,
    )


@pytest.mark.django_db
class TestPortfolioList:
    def test_list_own_portfolios(self, auth_client, portfolio):
        url = reverse('portfolio-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['name'] == 'Minha Carteira'

    def test_cannot_see_other_users_portfolios(self, auth_client, other_user, db):
        Portfolio.objects.create(user=other_user, name='Carteira alheia')
        url = reverse('portfolio-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_unauthenticated_returns_401(self, api_client):
        url = reverse('portfolio-list')
        response = api_client.get(url)
        assert response.status_code == 401


@pytest.mark.django_db
class TestPortfolioCreate:
    def test_create_portfolio(self, auth_client):
        url = reverse('portfolio-list')
        response = auth_client.post(url, {'name': 'Nova Carteira'})
        assert response.status_code == 201
        assert response.data['name'] == 'Nova Carteira'

    def test_create_without_name_fails(self, auth_client):
        url = reverse('portfolio-list')
        response = auth_client.post(url, {})
        assert response.status_code == 400


@pytest.mark.django_db
class TestPortfolioDetail:
    def test_get_portfolio(self, auth_client, portfolio):
        url = reverse('portfolio-detail', kwargs={'pk': portfolio.pk})
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.data['name'] == portfolio.name

    def test_update_portfolio(self, auth_client, portfolio):
        url = reverse('portfolio-detail', kwargs={'pk': portfolio.pk})
        response = auth_client.patch(url, {'name': 'Carteira Editada'})
        assert response.status_code == 200
        assert response.data['name'] == 'Carteira Editada'

    def test_delete_portfolio(self, auth_client, portfolio):
        url = reverse('portfolio-detail', kwargs={'pk': portfolio.pk})
        response = auth_client.delete(url)
        assert response.status_code == 204
        assert not Portfolio.objects.filter(pk=portfolio.pk).exists()

    def test_cannot_access_other_users_portfolio(self, auth_client, other_user, db):
        other_portfolio = Portfolio.objects.create(user=other_user, name='Alheia')
        url = reverse('portfolio-detail', kwargs={'pk': other_portfolio.pk})
        response = auth_client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestAssets:
    def test_list_assets(self, auth_client, portfolio, asset):
        url = reverse('asset-list', kwargs={'portfolio_pk': portfolio.pk})
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['ticker'] == 'PETR4'

    def test_create_asset(self, auth_client, portfolio):
        url = reverse('asset-list', kwargs={'portfolio_pk': portfolio.pk})
        data = {'ticker': 'VALE3', 'name': 'Vale', 'asset_type': 'stock'}
        response = auth_client.post(url, data)
        assert response.status_code == 201
        assert response.data['ticker'] == 'VALE3'

    def test_duplicate_ticker_in_same_portfolio_fails(self, auth_client, portfolio, asset):
        url = reverse('asset-list', kwargs={'portfolio_pk': portfolio.pk})
        data = {'ticker': 'PETR4', 'name': 'Petrobras', 'asset_type': 'stock'}
        response = auth_client.post(url, data)
        assert response.status_code == 400

    def test_delete_asset(self, auth_client, portfolio, asset):
        url = reverse('asset-detail', kwargs={'portfolio_pk': portfolio.pk, 'pk': asset.pk})
        response = auth_client.delete(url)
        assert response.status_code == 204
        assert not Asset.objects.filter(pk=asset.pk).exists()

    def test_asset_in_nonexistent_portfolio_returns_404(self, auth_client):
        url = reverse('asset-list', kwargs={'portfolio_pk': 9999})
        response = auth_client.get(url)
        assert response.status_code == 404
