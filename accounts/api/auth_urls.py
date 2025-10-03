from django.urls import path
from .auth_views import CPFTokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("token/", CPFTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
