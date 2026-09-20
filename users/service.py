import boto3
from django.conf import settings

_client = boto3.client('cognito-idp', region_name=settings.COGNITO_REGION)


class _Resp:
    """Imita a interface de um response do requests (.ok / .status_code / .json())."""
    def __init__(self, ok, status_code, data=None):
        self.ok = ok
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class CognitoService:

    @staticmethod
    def register_user(data):
        email = data['email']
        password = data['password']
        try:
            _client.admin_create_user(
                UserPoolId=settings.COGNITO_USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'},
                ],
                MessageAction='SUPPRESS',
                TemporaryPassword=password,
            )
            _client.admin_set_user_password(
                UserPoolId=settings.COGNITO_USER_POOL_ID,
                Username=email,
                Password=password,
                Permanent=True,
            )
            return _Resp(True, 201)
        except _client.exceptions.UsernameExistsException:
            return _Resp(False, 409)
        except Exception:
            return _Resp(False, 400)

    @staticmethod
    def login(email, password):
        try:
            resp = _client.initiate_auth(
                ClientId=settings.COGNITO_APP_CLIENT_ID,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={'USERNAME': email, 'PASSWORD': password},
            )
            result = resp['AuthenticationResult']
            return _Resp(True, 200, {
                'access_token': result['AccessToken'],
                'refresh_token': result.get('RefreshToken', ''),
            })
        except (_client.exceptions.NotAuthorizedException,
                _client.exceptions.UserNotFoundException):
            return _Resp(False, 401)
        except Exception:
            return _Resp(False, 503)

    @staticmethod
    def refresh(refresh_token):
        try:
            resp = _client.initiate_auth(
                ClientId=settings.COGNITO_APP_CLIENT_ID,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={'REFRESH_TOKEN': refresh_token},
            )
            result = resp['AuthenticationResult']
            return _Resp(True, 200, {
                'access_token': result['AccessToken'],
                # o Cognito não reemite o refresh token nesse fluxo, então devolvemos o mesmo
                'refresh_token': refresh_token,
            })
        except Exception:
            return _Resp(False, 401)

    @staticmethod
    def change_password(email, new_password):
        try:
            _client.admin_set_user_password(
                UserPoolId=settings.COGNITO_USER_POOL_ID,
                Username=email,
                Password=new_password,
                Permanent=True,
            )
            return _Resp(True, 200)
        except Exception:
            return _Resp(False, 500)