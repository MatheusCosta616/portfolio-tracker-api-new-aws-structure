from django.urls import path

from .controller import ChangePasswordView, LoginView, MeView, RefreshView, RegisterView

urlpatterns = [
    path('register', RegisterView.as_view(), name='auth-register'),
    path('login', LoginView.as_view(), name='auth-login'),
    path('refresh', RefreshView.as_view(), name='auth-refresh'),
    path('me', MeView.as_view(), name='auth-me'),
    path('me/change-password', ChangePasswordView.as_view(), name='auth-change-password'),
]
