from django.urls import path

from .controller import DeviceTokenView

urlpatterns = [
    path('device-token', DeviceTokenView.as_view(), name='device-token'),
]
