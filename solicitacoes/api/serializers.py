from rest_framework import serializers
from solicitacoes.models import Chamado


class ChamadoSerializer(serializers.ModelSerializer):
    # Nome legível do tipo (FK para TipoSolicitacao)
    tipo_nome = serializers.SerializerMethodField(read_only=True)
    # Rótulo legível do status (choices do model)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    # created_at compatível com o front (mapeia criado_em)
    created_at = serializers.SerializerMethodField(read_only=True)
    # nome do solicitante (só pra exibir)
    solicitante_nome = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Chamado
        fields = [
            "id",
            "tipo",            # id do TipoSolicitacao
            "tipo_nome",       # nome do tipo
            "status",
            "status_label",
            "solicitante",     # id do usuário
            "solicitante_nome",
            "created_at",
        ]
        read_only_fields = ["tipo_nome", "status_label", "solicitante", "solicitante_nome", "created_at"]

    # ----- getters -----
    def get_tipo_nome(self, obj):
        try:
            return obj.tipo.nome
        except Exception:
            return None

    def get_created_at(self, obj):
        # compatibilidade: criado_em -> created_at
        return getattr(obj, "criado_em", None)

    def get_solicitante_nome(self, obj):
        u = getattr(obj, "solicitante", None)
        if not u:
            return None
        # tenta full_name; se vazio, usa str(user)
        full = getattr(u, "get_full_name", lambda: "")() or ""
        return full.strip() or str(u)
