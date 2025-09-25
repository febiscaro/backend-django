# Admin do Django (telas do /admin)
from django.contrib import admin
# Formulários e exceções para validação
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CostCenter, AllowedDomain, CostCenterMember,  
    Project, Task, DOW, DOW_ORDER)         

# -------------------------------------------------------------------
# FORM DO ADMIN PARA CostCenter
# - Aqui validamos o campo "contato_email" usando:
#   1) Domínios JÁ salvos no banco (se o centro já existir)
#   2) Domínios digitados nos INLINES desta mesma tela (POST)
# -------------------------------------------------------------------
class CostCenterAdminForm(forms.ModelForm):
    class Meta:
        model = CostCenter
        fields = "__all__"

    def clean_contato_email(self):
        """
        Rejeita e-mail do contato se o domínio não estiver na lista de
        'Domínios permitidos' (ativos) — considera tanto os já existentes
        quanto os que o usuário digitou agora nos inlines.
        """
        email = (self.cleaned_data.get("contato_email") or "").strip()
        if not email:
            return email  # campo é opcional, então vazio é permitido

        if "@" not in email:
            raise ValidationError("Informe um e-mail válido (faltou @).")

        # Domínio do e-mail informado no formulário do CostCenter
        domain = email.rsplit("@", 1)[-1].lower()

        allowed = set()

        # 1) Domínios JÁ SALVOS no banco (apenas se o centro já existe)
        instance = self.instance
        if instance and instance.pk:
            qs = instance.dominios_permitidos.filter(ativo=True).values_list("dominio", flat=True)
            allowed.update(d.lower() for d in qs)

        # 2) Domínios digitados AGORA nos inlines (antes de salvar)
        #    O prefixo padrão do inline fica igual ao related_name do FK:
        #    'dominios_permitidos'. Django envia no POST chaves como:
        #    dominios_permitidos-TOTAL_FORMS, dominios_permitidos-0-dominio, etc.
        data = self.data
        prefix = "dominios_permitidos"
        try:
            total = int(data.get(f"{prefix}-TOTAL_FORMS", 0))
        except (TypeError, ValueError):
            total = 0

        for i in range(total):
            dom = (data.get(f"{prefix}-{i}-dominio") or "").strip().lower()
            ativo_val = data.get(f"{prefix}-{i}-ativo")      # checkbox -> existe se marcado
            delete_marked = data.get(f"{prefix}-{i}-DELETE") # checkbox de apagar inline

            # Se tem domínio digitado, marcado como ativo e não marcado para deletar,
            # consideramos como permitido na validação
            if dom and ativo_val and not delete_marked:
                allowed.add(dom)

        # Regra: se EXISTE pelo menos um domínio permitido (banco ou inline),
        # o e-mail do contato precisa pertencer a um desses domínios.
        if allowed and domain not in allowed:
            lista = ", ".join(sorted(allowed))
            raise ValidationError(f"O domínio do e-mail do contato deve estar entre os permitidos: {lista}.")

        return email


# -------------------------------------------------------------------
# INLINE: editar AllowedDomain (filho) dentro do form do CostCenter (pai)
# -------------------------------------------------------------------
class AllowedDomainInline(admin.TabularInline):
    model = AllowedDomain
    extra = 1
    fields = ("dominio", "ativo")
    show_change_link = True


# -------------------------------------------------------------------
# ADMIN DO CostCenter
# -------------------------------------------------------------------
@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    # Usa o form acima com a validação do contato_email
    form = CostCenterAdminForm

    # Colunas na listagem
    list_display = (
        "nome", "codigo", "cliente", "ativo",
        "contrato_inicio", "contrato_fim",
        "orcamento_total", "horas_previstas",
        "criado_em",
    )
    list_filter  = ("ativo",)
    search_fields = ("nome", "codigo", "cliente")

    # Mostra os domínios como inline dentro do formulário do centro
    inlines = [AllowedDomainInline]

    # Organiza o formulário por seções
    fieldsets = (
        ("Identificação", {
            "fields": ("nome", "codigo", "cliente", "ativo")
        }),
        ("Contato", {
            "fields": ("contato_nome", "contato_email", "contato_telefone"),
            "classes": ("collapse",)
        }),
        ("Contrato & Recursos", {
            "fields": ("contrato_inicio", "contrato_fim", "orcamento_total", "horas_previstas")
        }),
        ("Auditoria", {
            "fields": ("criado_em", "atualizado_em"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("criado_em", "atualizado_em")


# -------------------------------------------------------------------
# ADMIN do AllowedDomain (página própria, além do inline)
# -------------------------------------------------------------------
@admin.register(AllowedDomain)
class AllowedDomainAdmin(admin.ModelAdmin):
    list_display = ("dominio", "centro", "ativo", "criado_em")
    list_filter  = ("ativo", "centro")
    search_fields = ("dominio", "centro__nome")




@admin.register(CostCenterMember)
class CostCenterMemberAdmin(admin.ModelAdmin):
    """Gerencia quem pertence a cada centro e com qual papel."""
    list_display = ("centro", "usuario", "papel", "ativo", "criado_em")
    list_filter  = ("papel", "ativo", "centro")
    search_fields = (
        "centro__nome",
        "usuario__username", "usuario__first_name", "usuario__last_name", "usuario__email",
    )
    # Evita carregar milhares de usuários num select gigante; abre um popup de busca
    raw_id_fields = ("usuario",)




# Aqui começa os registros no django adm com os dados que o gestor usa para criar a atrefa

from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CostCenter, AllowedDomain, CostCenterMember,  # já existiam
    Project, Task, DOW, DOW_ORDER                 # <-- novos imports
)

# --------------------------------------------------------------------
# (já existentes) CostCenterAdmin, AllowedDomainAdmin, etc.
# ... mantenha seu código anterior aqui ...
# --------------------------------------------------------------------


# =========================
# ADMIN: Project (projetos)
# =========================
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """
    Cadastro de Projetos por Centro de Custo.
    Vai aparecer como 'lista suspensa' ao criar Task.
    """
    list_display  = ("nome", "centro", "ativo")
    list_filter   = ("ativo", "centro")
    search_fields = ("nome", "centro__nome")
    autocomplete_fields = ("centro",)  # se a lista de centros crescer muito


# ===============================================
# Form amigável para Task (checkbox de dias/recorrência)
# ===============================================
class TaskAdminForm(forms.ModelForm):
    # Campo "amigável" para os dias (múltipla escolha); mapearemos para a bitmask internamente
    dias = forms.MultipleChoiceField(
        required=False,
        choices=DOW_ORDER,         # [("MON","Seg"), ...]
        widget=forms.CheckboxSelectMultiple,
        label="Dias da semana"
    )

    class Meta:
        model = Task
        fields = [
            "centro", "projeto",
            "nome", "orientacoes",
            "autorizados",
            "data_inicio_prevista", "data_fim_prevista",
            "horas_homem_previstas",
            "hora_publicacao", "encerra_no_fim_do_dia",
            "status",
            # 'dias' NÃO está no model; entra pelo form
        ]
        widgets = {
            "orientacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        """
        - Preenche o campo 'dias' do form a partir da máscara salva (quando editando).
        - (Opcional) poderia filtrar 'projeto' por 'centro' aqui, mas deixamos simples por enquanto.
        """
        super().__init__(*args, **kwargs)

        # quando editando, mostra dias marcados
        instance = self.instance
        if instance and instance.pk:
            marcados = []
            for key, _label in DOW_ORDER:
                if instance.recorrencia_dias & DOW[key]:
                    marcados.append(key)
            self.fields["dias"].initial = marcados

    def clean(self):
        """
        - Garante que o projeto pertence ao mesmo centro (reforço de segurança).
        - Converte 'dias' (checkboxes) em 'recorrencia_dias' (bitmask).
        - Valida datas coerentes.
        """
        cleaned = super().clean()

        centro  = cleaned.get("centro")
        projeto = cleaned.get("projeto")
        if centro and projeto and projeto.centro_id != centro.id:
            raise ValidationError({"projeto": "O projeto escolhido não pertence a este Centro de Custo."})

        # dias -> bitmask
        keys = cleaned.get("dias") or []
        mask = 0
        for k in keys:
            mask |= DOW.get(k, 0)
        cleaned["recorrencia_dias"] = mask  # guardamos para usar no save

        # datas coerentes (o Model.clean também verifica, mas mantemos aqui para erro no form)
        di = cleaned.get("data_inicio_prevista")
        df = cleaned.get("data_fim_prevista")
        if di and df and df < di:
            raise ValidationError({"data_fim_prevista": "Fim previsto não pode ser antes do início."})

        return cleaned

    def save(self, commit=True):
        """
        - Escreve a bitmask no model antes de salvar.
        - O 'criado_por' será setado no admin (save_model).
        """
        obj = super().save(commit=False)
        obj.recorrencia_dias = self.cleaned_data.get("recorrencia_dias", 0)
        if commit:
            obj.save()
            # M2M
            self.save_m2m()
        return obj


# ======================
# ADMIN: Task (tarefas)
# ======================
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """
    Cadastro de Tarefas. Form amigável para recorrência (dias) e salvando 'criado_por' automático.
    """
    form = TaskAdminForm

    list_display  = ("nome", "centro", "projeto", "status", "data_inicio_prevista", "data_fim_prevista", "criado_por", "criado_em")
    list_filter   = ("status", "centro", "projeto")
    search_fields = ("nome", "projeto__nome", "centro__nome", "autorizados__username", "autorizados__email")
    autocomplete_fields = ("centro", "projeto")   # ajuda quando crescer
    filter_horizontal   = ("autorizados",)        # UI melhor para M2M

    readonly_fields = ("criado_em", "atualizado_em")

    fieldsets = (
        ("Contexto", {
            "fields": ("centro", "projeto", "status")
        }),
        ("Conteúdo", {
            "fields": ("nome", "orientacoes")
        }),
        ("Autorizados", {
            "fields": ("autorizados",),
            "description": "Selecione as pessoas que poderão lançar atividades nesta tarefa."
        }),
        ("Planejamento", {
            "fields": ("data_inicio_prevista", "data_fim_prevista", "horas_homem_previstas")
        }),
        ("Recorrência diária", {
            "fields": ("dias", "hora_publicacao", "encerra_no_fim_do_dia"),
            "description": "Marque os dias que a tarefa aparece e, opcionalmente, o horário. Se habilitado, ela encerra às 23:59 do mesmo dia."
        }),
        ("Auditoria", {
            "fields": ("criado_em", "atualizado_em"),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        """
        Preenche 'criado_por' automaticamente na criação.
        """
        if not change or not obj.criado_por_id:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)
