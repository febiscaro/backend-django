from rest_framework import serializers
from solicitacoes.models import Chamado

class ChamadoSerializer(serializers.ModelSerializer):
    # Campos "seguros" (não quebram se não houver choices)
    tipo_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    # Sempre expomos created_at, mapeando para o nome que existir no modelo
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = Chamado
        fields = [
            'id',
            'status', 'status_label',
            'tipo', 'tipo_label',
            'solicitante',
            'created_at',
        ]

    # --- helpers robustos ---
    def get_tipo_label(self, obj):
        # se for choices, usa o display; senão, devolve o próprio valor legível
        if hasattr(obj, 'get_tipo_display'):
            try:
                return obj.get_tipo_display()
            except Exception:
                pass
        val = getattr(obj, 'tipo', None)
        return str(val) if val is not None else None

    def get_status_label(self, obj):
        if hasattr(obj, 'get_status_display'):
            try:
                return obj.get_status_display()
            except Exception:
                pass
        val = getattr(obj, 'status', None)
        return str(val) if val is not None else None

    def get_created_at(self, obj):
        # tenta vários nomes comuns
        for name in ('created_at', 'created', 'criado_em', 'data_criacao'):
            if hasattr(obj, name):
                return getattr(obj, name)
        return None
