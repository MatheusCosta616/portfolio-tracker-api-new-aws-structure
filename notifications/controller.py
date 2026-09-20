from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import DeviceToken
from .dto import DeviceTokenSerializer


class DeviceTokenView(generics.GenericAPIView):
    serializer_class = DeviceTokenSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        """Register or reactivate a device token."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token, created = DeviceToken.objects.update_or_create(
            token=serializer.validated_data['token'],
            defaults={
                'user': request.user,
                'platform': serializer.validated_data['platform'],
                'is_active': True,
            },
        )
        out = DeviceTokenSerializer(token)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(out.data, status=status_code)

    def delete(self, request):
        """Deactivate a device token (logout from push notifications)."""
        token_value = request.data.get('token')
        if not token_value:
            return Response({'detail': 'token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        updated = DeviceToken.objects.filter(
            token=token_value, user=request.user
        ).update(is_active=False)

        if not updated:
            return Response({'detail': 'Token not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
