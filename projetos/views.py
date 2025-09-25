from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404
from .models import CostCenter, CostCenterMember,AllowedDomain,Task
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from .forms import CostCenterCreateForm
from collections import OrderedDict




def _is_gestor(user) -> bool:
    """
    Regra de acesso: só superusuário OU quem for Gestor em pelo menos um centro.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return CostCenterMember.objects.filter(
        usuario=user,
        papel=CostCenterMember.Role.GESTOR,
        ativo=True
    ).exists()


@login_required
@user_passes_test(_is_gestor)  # só gestor/superuser acessam
def centros_list(request):
    """
    Primeira versão: lista os centros que o usuário GESTOR gerencia.
    Superusuário vê todos.
    (Depois faremos o HTML bonitinho em cards.)
    """
    if request.user.is_superuser:
        centros = CostCenter.objects.order_by("nome")
    else:
        centros = CostCenter.objects.filter(
            membros__usuario=request.user,
            membros__papel=CostCenterMember.Role.GESTOR,
            membros__ativo=True,
        ).order_by("nome").distinct()

    # Versão 1: página simples (sem template ainda)
    # Trocaremos por template em seguida; agora é só pra validar a rota/permissão.
    return render(request, "projetos/centros_list.html", {"centros": centros})





@login_required
@user_passes_test(_is_gestor)
@require_POST
def centros_create(request):
    """
    Cria um Centro de Custo via modal (AJAX/Fetch).
    Permissão: Gestor ou Superusuário.
    """
    form = CostCenterCreateForm(request.POST, request.FILES)
    if form.is_valid():
        dominios = form.cleaned_data.pop("dominios", [])
        center = form.save()  # cria o CostCenter

        # cria domínios permitidos (ativos)
        objs = [AllowedDomain(centro=center, dominio=d, ativo=True) for d in dominios]
        if objs:
            AllowedDomain.objects.bulk_create(objs, ignore_conflicts=True)

        bg_url = center.background_image.url if center.background_image else ""
        return JsonResponse({
            "ok": True,
            "center": {
                "id": str(center.id),
                "nome": center.nome,
                "codigo": center.codigo,
                "cliente": center.cliente or "",
                "background_image_url": bg_url,
            }
        })
    # erros de validação
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)







@login_required
@user_passes_test(_is_gestor)  # só gestor/superuser acessam páginas de gestão
def board(request, centro_id):
    """
    Board de gestão do Centro de Custo.
    - Mostra as tarefas do centro, agrupadas por Status (Aberta, Em andamento, ...).
    - Próximos passos: filtro por data/recorrência e drag-and-drop.
    """
    centro = get_object_or_404(CostCenter, pk=centro_id)

    # Segurança extra: se não for superuser, precisa ser Gestor *deste* centro
    if not request.user.is_superuser:
        autorizado = CostCenterMember.objects.filter(
            centro=centro,
            usuario=request.user,
            papel=CostCenterMember.Role.GESTOR,
            ativo=True,
        ).exists()
        if not autorizado:
            return HttpResponseForbidden("Você não tem permissão neste centro.")

    # Busca tarefas do centro e prepara colunas por status
    qs = Task.objects.filter(centro=centro).select_related("projeto").prefetch_related("autorizados")

    columns = OrderedDict([
        (Task.Status.ABERTA,       {"label": "Aberta",        "items": []}),
        (Task.Status.EM_ANDAMENTO, {"label": "Em andamento",  "items": []}),
        (Task.Status.PAUSADA,      {"label": "Pausada",       "items": []}),
        (Task.Status.EM_AVALIACAO, {"label": "Em avaliação",  "items": []}),
        (Task.Status.CONCLUIDA,    {"label": "Concluída",     "items": []}),
    ])
    for t in qs:
        columns[t.status]["items"].append(t)

    context = {
        "centro": centro,
        "columns": columns,  # dict: status -> {label, items[]}
    }
    return render(request, "projetos/board.html", context)
