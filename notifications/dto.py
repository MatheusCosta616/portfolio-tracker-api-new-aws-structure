from rest_framework import serializers
from .models import DeviceToken


class DeviceTokenSerializer(serializers.ModelSerializer):
    token = serializers.CharField(max_length=255, validators=[])

    class Meta:
        model = DeviceToken
        fields = ('id', 'token', 'platform', 'is_active', 'created_at')
        read_only_fields = ('id', 'is_active', 'created_at')
