import logging

from django.db import IntegrityError
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from news.models import Analysis
from news.dto import AnalysisSerializer
from .models import Asset, Portfolio
from .dto import AssetSerializer, PortfolioListSerializer, PortfolioSerializer

logger = logging.getLogger(__name__)


class PortfolioListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return PortfolioListSerializer
        return PortfolioSerializer

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PortfolioDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PortfolioSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)


class AssetListCreateView(generics.ListCreateAPIView):
    serializer_class = AssetSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def _get_portfolio(self):
        try:
            return Portfolio.objects.get(pk=self.kwargs['portfolio_pk'], user=self.request.user)
        except Portfolio.DoesNotExist:
            raise NotFound('Portfolio not found.')

    def get_queryset(self):
        return Asset.objects.filter(portfolio=self._get_portfolio())

    def perform_create(self, serializer):
        try:
            asset = serializer.save(portfolio=self._get_portfolio())
        except IntegrityError:
            raise ValidationError({'ticker': 'This ticker already exists in the portfolio.'})


class AssetDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = AssetSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        try:
            portfolio = Portfolio.objects.get(pk=self.kwargs['portfolio_pk'], user=self.request.user)
        except Portfolio.DoesNotExist:
            raise NotFound('Portfolio not found.')
        return Asset.objects.filter(portfolio=portfolio)


class PortfolioAnalyseView(APIView):
    """POST: queue portfolio news fetch and sentiment analysis.

    The response is intentionally asynchronous: poll the portfolio ``analyses``
    endpoint for pending, processing, completed, or failed analysis rows.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def _get_portfolio(self, user, pk):
        try:
            return Portfolio.objects.get(pk=pk, user=user)
        except Portfolio.DoesNotExist:
            raise NotFound('Portfolio not found.')

    def post(self, request, portfolio_pk):
        portfolio = self._get_portfolio(request.user, portfolio_pk)
        tickers = list(portfolio.assets.values_list('ticker', flat=True).distinct())

        if not tickers:
            return Response(
                {'detail': 'A carteira não possui ativos para analisar.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .tasks import analyse_portfolio

        task = analyse_portfolio.apply_async(args=(portfolio.pk, tickers))
        return Response(
            {'task_id': task.id, 'status': 'queued'},
            status=status.HTTP_202_ACCEPTED,
        )


class PortfolioAnalysisListView(generics.ListAPIView):
    """GET: list all sentiment analyses for the tickers in a portfolio."""
    serializer_class = AnalysisSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        try:
            portfolio = Portfolio.objects.get(
                pk=self.kwargs['portfolio_pk'], user=self.request.user
            )
        except Portfolio.DoesNotExist:
            raise NotFound('Portfolio not found.')

        tickers = list(portfolio.assets.values_list('ticker', flat=True).distinct())
        return (
            Analysis.objects.filter(ticker__in=tickers)
            .select_related('article')
            .order_by('-created_at')
        )
