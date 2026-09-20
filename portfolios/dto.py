from rest_framework import serializers
from .models import Asset, Portfolio


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ('id', 'ticker', 'name', 'asset_type', 'created_at')
        read_only_fields = ('id', 'created_at')


class PortfolioSerializer(serializers.ModelSerializer):
    assets = AssetSerializer(many=True, read_only=True)
    asset_count = serializers.IntegerField(source='assets.count', read_only=True)

    class Meta:
        model = Portfolio
        fields = ('id', 'name', 'asset_count', 'assets', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class PortfolioListSerializer(serializers.ModelSerializer):
    asset_count = serializers.IntegerField(source='assets.count', read_only=True)

    class Meta:
        model = Portfolio
        fields = ('id', 'name', 'asset_count', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')
