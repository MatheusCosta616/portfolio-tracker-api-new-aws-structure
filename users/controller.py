from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model

from .dto import ChangePasswordSerializer, RegisterSerializer, UserSerializer
from .service import CognitoService as KeycloakService

User = get_user_model()


class RegisterView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            resp = KeycloakService.register_user(data)
        except Exception:
            return Response(
                {'detail': 'Não foi possível conectar ao servidor de autenticação.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if resp.status_code == 409:
            return Response({'detail': 'E-mail já cadastrado.'}, status=status.HTTP_400_BAD_REQUEST)

        if not resp.ok:
            return Response({'detail': 'Erro ao criar conta.'}, status=status.HTTP_400_BAD_REQUEST)

        User.objects.get_or_create(
            email=data['email'],
            defaults={'username': data['username']},
        )

        return Response({'email': data['email'], 'username': data['username']}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Proxies login to Keycloak and returns access + refresh tokens."""
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        email = request.data.get('email', '')
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'detail': 'Email e senha são obrigatórios.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resp = KeycloakService.login(email, password)
        except Exception:
            return Response(
                {'detail': 'Não foi possível conectar ao servidor de autenticação.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if resp.status_code in (401, 400):
            return Response({'detail': 'Credenciais inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not resp.ok:
            return Response({'detail': 'Erro ao autenticar.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        User.objects.get_or_create(email=email, defaults={'username': email})
        data = resp.json()
        return Response({
            'access': data['access_token'],
            'refresh': data['refresh_token'],
        })


class RefreshView(APIView):
    """Proxies refresh token to Keycloak and returns new access + refresh tokens."""
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        refresh_token = request.data.get('refresh', '')
        if not refresh_token:
            return Response({'detail': 'Refresh token é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resp = KeycloakService.refresh(refresh_token)
        except Exception:
            return Response(
                {'detail': 'Não foi possível conectar ao servidor de autenticação.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not resp.ok:
            return Response({'detail': 'Token de atualização inválido ou expirado.'}, status=status.HTTP_401_UNAUTHORIZED)

        data = resp.json()
        return Response({
            'access': data['access_token'],
            'refresh': data['refresh_token'],
        })


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            resp = KeycloakService.login(request.user.email, data['current_password'])
        except Exception:
            return Response(
                {'detail': 'Não foi possível conectar ao servidor de autenticação.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not resp.ok:
            return Response({'detail': 'Senha atual incorreta.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            KeycloakService.change_password(request.user.email, data['new_password'])
        except Exception:
            return Response({'detail': 'Erro ao alterar senha.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'detail': 'Senha alterada com sucesso.'})
