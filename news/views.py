from rest_framework import generics
from .models import Analysis
from .pagination import AnalysisPagination
from .serializers import AnalysisListSerializer, AnalysisDetailSerializer


class AnalysisListView(generics.ListAPIView):
    serializer_class = AnalysisListSerializer
    pagination_class = AnalysisPagination

    def get_queryset(self):
        # defer: a lista não traz os campos pesados (analise, last_error)
        qs = Analysis.objects.defer('analise', 'last_error')

        ticker = self.request.query_params.get('ticker')
        status = self.request.query_params.get('status')
        if ticker:
            qs = qs.filter(ticker=ticker)
        if status:
            qs = qs.filter(status=status)

        # aqui entra o filtro por usuário/carteira, se a view antiga tinha

        return qs.order_by('-created_at', '-id')


class AnalysisDetailView(generics.RetrieveAPIView):
    queryset = Analysis.objects.all()
    serializer_class = AnalysisDetailSerializer