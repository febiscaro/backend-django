from rest_framework import serializers
from solicitacoes.models import Chamado

class ChamadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chamado
        fields = "__all__"
        read_only_fields = ["id"]
