import json as _json

from rest_framework import serializers

from .models import Analysis


class AnalysisSerializer(serializers.ModelSerializer):
    article_title = serializers.CharField(source='article.title', read_only=True)
    article_url = serializers.URLField(source='article.url', read_only=True)
    result = serializers.SerializerMethodField()

    def get_result(self, obj):
        if not obj.analise:
            return None
        try:
            return _json.loads(obj.analise)
        except (ValueError, TypeError):
            return obj.analise

    class Meta:
        model = Analysis
        fields = (
            'id', 'ticker', 'status', 'result', 'model_version',
            'attempts', 'started_at', 'finished_at', 'created_at', 'updated_at',
            'article_title', 'article_url',
        )
        read_only_fields = fields


class LiveNewsArticleSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    title = serializers.CharField()
    summary = serializers.CharField()
    url = serializers.URLField()
    thumbnail_url = serializers.CharField()
    published_at = serializers.DateTimeField()
    source = serializers.SerializerMethodField()
    tickers = serializers.ListField(child=serializers.CharField(), source='related_tickers')

    def get_id(self, obj):
        return hash(obj.url) & 0x7FFFFFFF

    def get_source(self, obj):
        return {'id': 1, 'name': 'Yahoo Finance', 'slug': 'yfinance'}
