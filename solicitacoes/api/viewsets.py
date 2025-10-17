from rest_framework import viewsets, permissions, status
from rest_framework.response import Response

from solicitacoes.models import Chamado, ChamadoMensagem
from .serializers import ChamadoSerializer


class ChamadoViewSet(viewsets.ModelViewSet):
    queryset = Chamado.objects.all().order_by("-criado_em")
    serializer_class = ChamadoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        """
        Cria o chamado sempre com o solicitante = usuário do token.
        Status inicial segue o default do model ('aberto').
        Se 'descricao' vier no POST, grava como primeira mensagem pública.
        """
        instance = serializer.save(solicitante=self.request.user)
        desc = (self.request.data.get("descricao") or "").strip()
        if desc:
            ChamadoMensagem.objects.create(
                chamado=instance,
                autor=self.request.user,
                texto=desc,
                visibilidade=ChamadoMensagem.PUBLICA,
                tipo_evento="mensagem",
            )

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH tolerante para 'status':
        aceita 'Concluído', 'concluido', 'Em andamento', etc.
        """
        data = request.data.copy()
        if "status" in data:
            raw = str(data["status"]).strip().lower()
            mapa = {
                "concluído": "concluido",
                "concluido": "concluido",
                "em andamento": "em_andamento",
                "andamento": "em_andamento",
                "aberto": "aberto",
                "suspenso": "suspenso",
                "cancelado": "cancelado",
            }
            data["status"] = mapa.get(raw, raw)

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)
