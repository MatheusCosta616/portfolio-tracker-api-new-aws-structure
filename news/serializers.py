from rest_framework import serializers
from .models import Analysis


class AnalysisListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = ['id', 'article', 'ticker', 'status',
                  'model_version', 'created_at', 'finished_at']


class AnalysisDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = ['id', 'article', 'ticker', 'status', 'analise',
                  'model_version', 'attempts', 'last_error',
                  'started_at', 'finished_at', 'created_at', 'updated_at']