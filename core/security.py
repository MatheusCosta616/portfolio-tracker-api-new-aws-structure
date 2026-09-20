import boto3
import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()
_cognito = boto3.client('cognito-idp', region_name=settings.COGNITO_REGION)


class CognitoAuthentication(authentication.BaseAuthentication):
    keyword = 'Bearer'

    def authenticate_header(self, request):
        return self.keyword

    def get_jwks(self):
        jwks = cache.get('cognito_jwks')
        if jwks:
            return jwks
        try:
            response = requests.get(settings.COGNITO_JWKS_URL, timeout=5)
            response.raise_for_status()
            jwks = response.json()
        except Exception:
            raise AuthenticationFailed("Não foi possível obter as chaves públicas do Cognito.")
        cache.set('cognito_jwks', jwks, 3600)
        return jwks

    def get_email(self, sub, token):
        email = cache.get(f'cognito_email:{sub}')
        if email:
            return email
        try:
            info = _cognito.get_user(AccessToken=token)
            email = next(a['Value'] for a in info['UserAttributes'] if a['Name'] == 'email')
        except Exception:
            raise AuthenticationFailed("Não foi possível obter o usuário no Cognito.")
        cache.set(f'cognito_email:{sub}', email, 3600)
        return email

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '').split()

        if not auth_header or auth_header[0] != self.keyword:
            return None
        if len(auth_header) == 1:
            raise AuthenticationFailed("Token inválido. Sem credenciais.")
        elif len(auth_header) > 2:
            raise AuthenticationFailed("Token inválido. Espaços não permitidos.")

        token = auth_header[1]

        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception:
            raise AuthenticationFailed("Token malformado.")

        rsa_key = {}
        for key in self.get_jwks().get('keys', []):
            if key['kid'] == unverified_header.get('kid'):
                rsa_key = {k: key[k] for k in ('kty', 'kid', 'use', 'n', 'e') if k in key}
                break
        if not rsa_key:
            raise AuthenticationFailed("Chave pública não encontrada para validar o token.")

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(rsa_key)
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=settings.COGNITO_ISSUER,
                options={"verify_aud": False},  # Access Token do Cognito não tem 'aud'
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("O token expirou.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Token inválido.")

        if payload.get('token_use') != 'access':
            raise AuthenticationFailed("Token não é um Access Token.")
        if payload.get('client_id') != settings.COGNITO_APP_CLIENT_ID:
            raise AuthenticationFailed("Token emitido para outro client.")

        email = self.get_email(payload['sub'], token)
        user, _ = User.objects.get_or_create(email=email, defaults={'username': email})
        return (user, token)