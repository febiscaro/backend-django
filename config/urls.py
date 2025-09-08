# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.forms import CPFAuthenticationForm, PrettyPasswordChangeForm
from solicitacoes.models import TipoSolicitacao   # ⬅️ add

def health(_):
    return HttpResponse("ok")

@login_required
def home(request):
    is_manager = (
        request.user.is_superuser
        or getattr(request.user, "perfil", "") == "ADMIN"
        or request.user.groups.filter(name="Gestor").exists()
    )
    tipos = list(TipoSolicitacao.objects.order_by("nome").values("id", "nome"))
    return render(request, "home.html", {"is_manager": is_manager, "tipos_solicitacao": tipos})



urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),

    # LOGIN / LOGOUT
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=CPFAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="password_change.html",
            form_class=PrettyPasswordChangeForm,
            success_url="/",
        ),
        name="password_change",
    ),

    # Apps
    path("accounts/", include("accounts.urls")),
    path("solicitacoes/", include(("solicitacoes.urls", "solicitacoes"), namespace="solicitacoes")),
    path("notifications/", include(("notifications.urls", "notifications"), namespace="notifications")),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
