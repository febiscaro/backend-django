from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User
from .forms import UserCreationForm, UserChangeForm

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    # 👇 inclui "gestao" nas colunas da lista
    list_display = (
        "nome_completo", "cpf", "email", "perfil", "gestao",
        "setor", "cargo", "is_active", "is_staff", "date_joined"
    )
    # 👇 e no filtro lateral
    list_filter = ("perfil", "gestao", "is_active", "is_staff", "setor", "cargo")
    search_fields = ("nome_completo", "cpf", "email")
    ordering = ("nome_completo",)

    # 👇 inclui "gestao" no formulário de edição
    fieldsets = (
        ("Dados pessoais", {
            "fields": (
                "cpf", "nome_completo", "email", "data_nascimento",
                "setor", "cargo", "perfil", "gestao"   # <-- aqui
            )
        }),
        ("Permissões", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        ("Informações de acesso", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("last_login", "date_joined")

    # 👇 inclui "gestao" no formulário de criação
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "cpf", "nome_completo", "email", "data_nascimento",
                "setor", "cargo", "perfil", "gestao",                # <-- aqui
                "password1", "password2", "is_active", "is_staff"
            )
        }),
    )

    actions = ["resetar_senha_temporaria", "ativar_usuarios", "desativar_usuarios"]

    @admin.action(description="Resetar senha temporária selecionados")
    def resetar_senha_temporaria(self, request, queryset):
        for user in queryset:
            temp = user.set_temporary_password()
            messages.info(request, f"Usuário {user.nome_completo} ({user.cpf}) senha temporária: {temp}")
        self.message_user(request, "Senhas temporárias geradas. Anote e envie aos usuários.", level=messages.SUCCESS)

    @admin.action(description="Ativar usuários selecionados")
    def ativar_usuarios(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} usuário(s) ativado(s).", level=messages.SUCCESS)

    @admin.action(description="Desativar usuários selecionados")
    def desativar_usuarios(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} usuário(s) desativado(s).", level=messages.WARNING)
