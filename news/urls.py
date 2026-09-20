from django.urls import path

from .controller import AnalysisDetailView, GlobalNewsListView, PortfolioNewsListView

urlpatterns = [
    path('', GlobalNewsListView.as_view(), name='news-global'),
    path('portfolio/<int:portfolio_pk>', PortfolioNewsListView.as_view(), name='news-portfolio'),
    path('analyses/<int:pk>', AnalysisDetailView.as_view(), name='analysis-detail'),
]
