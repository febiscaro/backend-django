from django.contrib import admin
from .models import TipoSolicitacao, PerguntaTipoSolicitacao, Chamado, RespostaChamado


class PerguntaInline(admin.TabularInline):
    model = PerguntaTipoSolicitacao
    extra = 1
    fields = ('ordem', 'texto', 'tipo_campo', 'obrigatoria', 'opcoes', 'ajuda', 'ativa')
    ordering = ('ordem',)


@admin.register(TipoSolicitacao)
class TipoSolicitacaoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo', 'criado_em')
    list_filter = ('ativo',)
    search_fields = ('nome', 'descricao')
    inlines = [PerguntaInline]


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo', 'solicitante', 'status', 'criado_em', 'atualizado_em')
    list_filter = ('status', 'tipo')
    search_fields = ('tratativa_adm', 'solicitante__username')


@admin.register(RespostaChamado)
class RespostaChamadoAdmin(admin.ModelAdmin):
    list_display = ('chamado', 'pergunta', 'valor_texto', 'valor_arquivo')
    search_fields = ('valor_texto', 'pergunta__texto', 'chamado__id')
