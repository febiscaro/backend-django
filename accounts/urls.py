from django.urls import path
from . import views
from .views import DashboardView, UsuarioListView, reset_password

app_name = "accounts"

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("usuarios/", UsuarioListView.as_view(), name="usuarios_list"),
    path("usuarios/<int:pk>/reset-senha/", reset_password, name="usuario_reset_senha"),
    path("perfil/", views.meu_perfil, name="perfil"),
]



