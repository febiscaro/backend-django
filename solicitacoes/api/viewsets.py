from rest_framework import viewsets, permissions
from solicitacoes.models import Chamado
from .serializers import ChamadoSerializer

class ChamadoViewSet(viewsets.ModelViewSet):
    queryset = Chamado.objects.all().order_by('-id')
    serializer_class = ChamadoSerializer
    permission_classes = [permissions.IsAuthenticated]
