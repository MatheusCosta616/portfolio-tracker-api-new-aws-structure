from django.urls import path

from .controller import (
    AssetDetailView,
    AssetListCreateView,
    PortfolioAnalysisListView,
    PortfolioAnalyseView,
    PortfolioDetailView,
    PortfolioListCreateView,
)

urlpatterns = [
    path('', PortfolioListCreateView.as_view(), name='portfolio-list'),
    path('<int:pk>', PortfolioDetailView.as_view(), name='portfolio-detail'),
    path('<int:portfolio_pk>/assets', AssetListCreateView.as_view(), name='asset-list'),
    path('<int:portfolio_pk>/assets/<int:pk>', AssetDetailView.as_view(), name='asset-detail'),
    path('<int:portfolio_pk>/analyse', PortfolioAnalyseView.as_view(), name='portfolio-analyse'),
    path('<int:portfolio_pk>/analyses', PortfolioAnalysisListView.as_view(), name='portfolio-analyses'),
]
