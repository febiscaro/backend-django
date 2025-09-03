from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, View
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.db.models import Q, Count
from django.urls import reverse

from .models import User


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("accounts.view_user", raise_exception=True), name="dispatch")
class UsuarioListView(ListView):
    """
    Lista de usuários com busca e paginação.
    Permissão: accounts.view_user
    """
    model = User
    template_name = "accounts/usuarios_list.html"
    context_object_name = "usuarios"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().order_by("nome_completo")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(nome_completo__icontains=q) |
                Q(cpf__icontains=q) |
                Q(email__icontains=q) |
                Q(setor__icontains=q) |
                Q(cargo__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs_all = User.objects.all()
        ctx["total"] = qs_all.count()
        ctx["ativos"] = qs_all.filter(is_active=True).count()
        ctx["por_perfil"] = qs_all.values("perfil").annotate(qtd=Count("id")).order_by("perfil")
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("accounts.view_user", raise_exception=True), name="dispatch")
class DashboardView(View):
    """
    Mantém /accounts/dashboard/ redirecionando para a lista de usuários.
    """
    def get(self, request):
        return redirect("accounts:usuarios_list")


@login_required
@permission_required("accounts.change_user", raise_exception=True)
def reset_password(request, pk: int):
    """
    Reseta a senha do usuário selecionado para uma senha temporária.
    Mostra a senha temporária via messages. Impede o usuário comum de
    resetar a própria senha por aqui.
    """
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("accounts:usuarios_list")

    alvo = get_object_or_404(User, pk=pk)

    if alvo.pk == request.user.pk and not request.user.is_superuser:
        messages.warning(request, "Você não pode resetar sua própria senha por aqui.")
        return redirect("accounts:usuarios_list")

    temp = alvo.set_temporary_password()
    messages.success(request, f"Senha temporária de {alvo.nome_completo} ({alvo.cpf}) é: {temp}")
    return redirect(f"{reverse('accounts:usuarios_list')}?q={alvo.cpf}")


@login_required
def meu_perfil(request):
    """
    Página de perfil somente leitura do usuário logado.
    Template: accounts/perfil.html
    """
    return render(request, "accounts/perfil.html")
