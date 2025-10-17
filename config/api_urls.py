from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ViewSets
from solicitacoes.api.viewsets import ChamadoViewSet

# Auth (JWT)
from accounts.api import auth_urls as accounts_auth_urls

router = DefaultRouter()
# >>> AQUI definimos /api/tickets/ <<<
router.register(r"tickets", ChamadoViewSet, basename="ticket")

urlpatterns = [
    # /api/tickets/ (lista/cria) e /api/tickets/<id>/ (detalhe/patch)
    path("", include(router.urls)),

    # /api/auth/token/  e  /api/auth/refresh/
    path("auth/", include(accounts_auth_urls)),
]
