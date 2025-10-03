from rest_framework_simplejwt.views import TokenRefreshView as _TokenRefreshView
from rest_framework_simplejwt.views import TokenObtainPairView as _TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CPFTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "cpf"  # seu AUTH_USER_MODEL usa CPF

class CPFTokenObtainPairView(_TokenObtainPairView):
    serializer_class = CPFTokenObtainPairSerializer

class TokenRefreshView(_TokenRefreshView):
    pass
