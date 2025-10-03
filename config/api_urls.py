from django.urls import path, include
from rest_framework.routers import DefaultRouter
from solicitacoes.api.viewsets import ChamadoViewSet

router = DefaultRouter()
router.register(r"tickets", ChamadoViewSet, basename="ticket")

urlpatterns = [
    path("", include(router.urls)),
]
