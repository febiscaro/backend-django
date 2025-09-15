# solicitacoes/urls.py
from django.urls import path, re_path
from . import views

app_name = "solicitacoes"



urlpatterns = [
    # --- Meus chamados (solicitante)
    path("meus-chamados/", views.meus_chamados, name="meus_chamados"),
    path("meus-chamados/nova/", views.nova_solicitacao, name="nova_solicitacao"),
    path("meus-chamados/campos/<int:tipo_id>/", views.form_campos_por_tipo, name="form_campos_por_tipo"),
    path("meus-chamados/reabrir/<int:pk>/", views.reabrir_chamado, name="reabrir_chamado"),
    path("meus-chamados/visto/<int:pk>/", views.marcar_conversa_vista, name="marcar_conversa_vista"),

    # --- Tratativa de chamado
    path("chamados/<int:pk>/", views.chamado_tratativa, name="chamado_tratativa"),
    path("chamados/<int:pk>/tratar/", views.tratar_chamado, name="tratar_chamado"),
    path("chamados/<int:pk>/abertura/", views.chamado_abertura_partial, name="chamado_abertura_partial"),
    path("chamados/<int:pk>/mensagens/", views.chamado_mensagens_partial, name="chamado_mensagens_partial"),
    path("chamados/<int:pk>/mensagens/enviar/", views.chamado_enviar_mensagem, name="chamado_enviar_mensagem"),

    # --- Administrativo
    path("atendimento/", views.gerenciar_chamados, name="gerenciar_chamados"),
    path("atendimento/assumir/<int:pk>/", views.assumir_chamado, name="assumir_chamado"),
    path("atendimento/abertos/fragment/", views.frag_abertos, name="frag_abertos"),

    # --- Tipos
    path("tipos/", views.tipos_list, name="tipos_list"),
    path("tipos/novo/", views.tipo_create, name="tipo_create"),
    path("tipos/<int:pk>/editar/", views.tipo_update, name="tipo_update"),
    path("tipos/<int:pk>/excluir/", views.tipo_delete, name="tipo_delete"),
    path("tipos/<int:pk>/perguntas/", views.tipo_perguntas, name="tipo_perguntas"),

    # --- Notificações / Vistos
    path("marcar-secao-vista/", views.marcar_secao_vista, name="marcar_secao_vista"),
    path("notificacoes/novas/", views.api_novas_mensagens, name="api_novas_mensagens"),
    path("atendimento/seen/", views._seen_alias, name="atendimento_seen"),
    path("marcar-vistos/", views.marcar_chamados_vistos, name="marcar_chamados_vistos"),

    # --- Legacy aliases
    re_path(r"^atendimento/seen$", views._seen_alias),   # sem barra final
    path("meus-chamados/seen/", views._seen_alias),


    # essas urls é do dash
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/data/", views.dashboard_data, name="dashboard-data"),
    path("dashboard/table/", views.dashboard_table, name="dashboard-table"),
    path("chamados/<int:pk>/modal/", views.chamado_modal, name="chamado-modal"),



    #pagine de controle de chamados e relatórios
    path("relatorio/", views.relatorio_solicitacoes, name="relatorio_solicitacoes"),
    path(
        "relatorio/chamado/<int:pk>/",
        views.relatorio_chamado_modal,
        name="relatorio_chamado_modal",
    ),
    path("relatorio/chamado/<int:pk>/", views.relatorio_chamado_modal, name="relatorio_chamado_modal"),
    path("relatorio/chamado/<int:pk>/delete/", views.relatorio_chamado_delete, name="relatorio_chamado_delete"),
    

]
