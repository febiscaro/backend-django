from django.urls import path
from . import views

app_name = "solicitacoes"

urlpatterns = [
    # Administração (superusuário)
    path("tipos/", views.tipos_list, name="tipos_list"),
    path("tipos/novo/", views.tipo_create, name="tipo_create"),
    path("tipos/<int:pk>/editar/", views.tipo_update, name="tipo_update"),
    path("tipos/<int:pk>/excluir/", views.tipo_delete, name="tipo_delete"),
    path("tipos/<int:pk>/perguntas/", views.tipo_perguntas, name="tipo_perguntas"),

    # Meus chamados (solicitante)
    path("meus-chamados/", views.meus_chamados, name="meus_chamados"),
    # <<< seen por ID de chamado (usado por sendSeenNow no JS)
    path("meus-chamados/seen/", views.marcar_chamados_vistos, name="meus_chamados_seen"),
    path("novo/", views.nova_solicitacao, name="nova_solicitacao"),
    path("form-campos/<int:tipo_id>/", views.form_campos_por_tipo, name="form_campos_por_tipo"),
    path("chamados/<int:pk>/reabrir/", views.reabrir_chamado, name="reabrir_chamado"),

    # Atendimento (administrativo)
    path("atendimento/", views.gerenciar_chamados, name="gerenciar_chamados"),
    path("atendimento/fragmentos/abertos/", views.frag_abertos, name="frag_abertos"),
    path("chamados/<int:pk>/assumir/", views.assumir_chamado, name="assumir_chamado"),
    path("chamados/<int:pk>/tratar/", views.tratar_chamado, name="tratar_chamado"),

    # Parciais e conversa do chamado
    path("chamados/<int:pk>/abertura/", views.chamado_abertura_partial, name="chamado_abertura_partial"),
    path("chamados/<int:pk>/mensagens/", views.chamado_mensagens_partial, name="chamado_mensagens_partial"),
    path("chamados/<int:pk>/mensagens/enviar/", views.chamado_enviar_mensagem, name="chamado_enviar_mensagem"),

    # Página de tratativa (deixe por último entre os /chamados/<pk>/...)
    path("chamados/<int:pk>/", views.chamado_tratativa, name="chamado_tratativa"),

    # Marca conversa aberta como vista (na tela do chamado)
    path("chamados/<int:pk>/visto/", views.marcar_conversa_vista, name="marcar_conversa_vista"),

    # Marca SEÇÃO (abertos/andamento/suspensos/concluídos/cancelados) como vista
    # Este nome é usado no template: {% url 'solicitacoes:marcar_secao_vista' %}
    path("atendimento/seen/", views.marcar_secao_vista, name="marcar_secao_vista"),


     path("atendimento/seen/", views.atendimento_seen, name="atendimento_seen"),

     path("notificacoes/novas/",views.api_novas_mensagens,name="api_novas_mensagens"),
]
