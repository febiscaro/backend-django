
import re
import time
from datetime import date, datetime, timedelta
from io import BytesIO
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, Paginator
from django.db import OperationalError, transaction
from django.db.models import Count, Max, Q
from django.forms import inlineformset_factory
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from accounts.models import User  # acesso às constantes de perfil
from .forms import (
    ChamadoMensagemForm,
    NovaSolicitacaoTipoForm,
    PerguntaTipoSolicitacaoForm,
    TipoSolicitacaoForm,
)
import json
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .models import (
    Chamado,
    ChamadoMensagem,
    ChamadoVista,
    PerguntaTipoSolicitacao,
    RespostaChamado,
    SecaoVista,
    TipoSolicitacao,
)


# Para onde voltar após mudança de status (admins)
NEXT_AFTER_STATUS_CHANGE = "solicitacoes:gerenciar_chamados"
UPDATED_FIELD = "atualizado_em"



from accounts.models import User  # garante acesso às constantes de perfil

def _perfil_is_admin(user) -> bool:
    # tolera variações antigas/novas e diferença de maiúsculas
    p = (getattr(user, "perfil", "") or "").strip().upper()
    return p in {getattr(User, "PERFIL_ADMIN", "ADMINISTRADOR"), "ADMIN", "ADMINISTRADOR", "ADMINISTRATIVO"}

def visible_chamados_for(user, base_qs):
    """
    Restringe 'base_qs' aos chamados visíveis pelo usuário.
    - Admin (perfil) ou superuser: tudo
    - Gestor: dele + equipe (mesma gestao ou grupo GESTAO_<gestao>)
    - Colaborador: apenas dele
    """
    if not user.is_authenticated:
        return base_qs.none()

    # >>> administrador (qualquer variação) ou superuser vê tudo
    if user.is_superuser or _perfil_is_admin(user):
        return base_qs

    # >>> gestor vê os próprios + equipe
    if (getattr(user, "perfil", "") or "").strip().upper() == "GESTOR":
        cond = Q(solicitante=user)
        gestao = (getattr(user, "gestao", "") or "").strip()
        if gestao and gestao.upper() != getattr(User, "GESTAO_SEM", "NA"):
            cond |= Q(solicitante__gestao=gestao) | Q(solicitante__groups__name=f"GESTAO_{gestao}")
        return base_qs.filter(cond).distinct()

    # >>> colaborador
    return base_qs.filter(solicitante=user)

# ----------------- helpers -----------------
def _is_assigned_to_me(user, ch) -> bool:
    """
    Retorna True se o nome do atendente do chamado coincide com o nome
    'exibível' do usuário atual (mesma regra que usamos ao salvar).
    """
    att = (getattr(ch, "atendente_nome", "") or "").strip().lower()
    me  = user_display(user).strip().lower()
    return bool(att) and att == me


def _eh_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False

    perfil = (getattr(user, "perfil", "") or "").strip().lower()
    if perfil in {"administrador", "administrativo", "admin"}:
        return True

    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    # grupos que você já usa no _is_adminish
    if user.groups.filter(name__in=["Administrativo", "Atendimento", "Gestor", "Suporte"]).exists():
        return True

    return False



def _is_finalizado_status(status):
    try:
        return status in {Chamado.Status.CONCLUIDO, Chamado.Status.CANCELADO}
    except Exception:
        s = str(status or "").strip().lower()
        return s in {"concluido", "concluído", "cancelado"}



def user_display(u):
    val = (getattr(u, "nome_completo", "") or "").strip()
    if val: return val
    gf = getattr(u, "get_full_name", None)
    if callable(gf):
        val = (gf() or "").strip()
        if val: return val
    first = (getattr(u, "first_name", "") or "").strip()
    last  = (getattr(u, "last_name", "") or "").strip()
    if first or last: return f"{first} {last}".strip()
    val = (getattr(u, "cpf", "") or "").strip()
    if val: return val
    gu = getattr(u, "get_username", None)
    if callable(gu):
        val = (gu() or "").strip()
        if val: return val
    return str(u)



def _is_adminish(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    if user.groups.filter(name__in=["Administrativo", "Atendimento", "Gestor", "Suporte"]).exists():
        return True
    perfil_val = str(getattr(user, "perfil", "") or "").strip().lower()
    if perfil_val in {"admin", "administrativo", "gestor", "atendimento", "suporte"}:
        return True
    if user.has_perm("solicitacoes.change_chamado"):
        return True
    return False

def admin_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if _is_adminish(request.user):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return _wrapped

def _pode_ver(user, chamado):
    return (
        _is_adminish(user)
        or user == getattr(chamado, "solicitante", None)
        or user == getattr(chamado, "atendente", None)
    )

def _updated_filter(qs, last_seen):
    try:
        return qs.filter(**{f"{UPDATED_FIELD}__gt": last_seen})
    except Exception:
        return qs.filter(criado_em__gt=last_seen)

def _last_seen(user, secao: str):
    epoch = timezone.make_aware(timezone.datetime(1970, 1, 1))
    obj, _ = SecaoVista.objects.get_or_create(user=user, secao=secao, defaults={"last_seen": epoch})
    return obj.last_seen

def _paginar(qs, per_page, page_param, request):
    paginator = Paginator(qs, per_page)
    try:
        page_number = int(request.GET.get(page_param) or 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        return paginator.page(page_number)
    except EmptyPage:
        return paginator.page(1)

def _encode_filters_without_pages(request):
    qs = request.GET.copy()
    for k in ["pg_a", "pg_and", "pg_sus", "pg_con", "pg_can"]:
        qs.pop(k, None)
    return urlencode(qs, doseq=True)

# ----------------- admin (Tipos) -----------------

def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_superuser)(view_func)

@superuser_required
def tipos_list(request):
    tipos = TipoSolicitacao.objects.all().order_by("nome")
    return render(request, "solicitacoes/tipos_list.html", {"tipos": tipos})

@superuser_required
def tipo_create(request):
    if request.method == "POST":
        form = TipoSolicitacaoForm(request.POST)
        if form.is_valid():
            tipo = form.save()
            messages.success(request, "Tipo criado com sucesso.")
            return redirect("solicitacoes:tipo_perguntas", pk=tipo.pk)
    else:
        form = TipoSolicitacaoForm()
    return render(request, "solicitacoes/tipo_form.html", {"form": form, "titulo": "Novo Tipo"})

@superuser_required
def tipo_update(request, pk):
    tipo = get_object_or_404(TipoSolicitacao, pk=pk)
    if request.method == "POST":
        form = TipoSolicitacaoForm(request.POST, instance=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo atualizado com sucesso.")
            return redirect("solicitacoes:tipo_perguntas", pk=tipo.pk)
    else:
        form = TipoSolicitacaoForm(instance=tipo)
    return render(request, "solicitacoes/tipo_form.html", {"form": form, "titulo": f"Editar Tipo: {tipo.nome}"})

@superuser_required
def tipo_delete(request, pk):
    tipo = get_object_or_404(TipoSolicitacao, pk=pk)
    if request.method == "POST":
        tipo.delete()
        messages.success(request, "Tipo excluído com sucesso.")
        return redirect("solicitacoes:tipos_list")
    return render(request, "solicitacoes/tipo_delete_confirm.html", {"tipo": tipo})

@superuser_required
def tipo_perguntas(request, pk):
    tipo = get_object_or_404(TipoSolicitacao, pk=pk)
    PerguntaFormSet = inlineformset_factory(
        TipoSolicitacao,
        PerguntaTipoSolicitacao,
        form=PerguntaTipoSolicitacaoForm,
        extra=1,
        can_delete=True,
        fields=("ordem", "texto", "tipo_campo", "obrigatoria", "opcoes", "ajuda", "ativa"),
    )
    if request.method == "POST":
        form = TipoSolicitacaoForm(request.POST, instance=tipo)
        formset = PerguntaFormSet(request.POST, instance=tipo)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Perguntas salvas com sucesso.")
            return redirect("solicitacoes:tipos_list")
    else:
        form = TipoSolicitacaoForm(instance=tipo)
        formset = PerguntaFormSet(instance=tipo)

    return render(request, "solicitacoes/tipo_perguntas.html", {"tipo": tipo, "form": form, "formset": formset})

# ----------------- Meus Chamados (solicitante) -----------------

from accounts.models import User  # (garanta esse import no topo do arquivo)

@login_required
def meus_chamados(request):
    # Perfil ADMINISTRADOR não usa "Meus Chamados" (a menos que seja superuser)
    if (not request.user.is_superuser) and getattr(request.user, "perfil", None) == User.PERFIL_ADMIN:
        return redirect("solicitacoes:gerenciar_chamados")

    qs_base = (
        Chamado.objects.filter(solicitante=request.user)
        .select_related("tipo")
        .prefetch_related("respostas")
        .order_by("-criado_em")
    )

    abertos_qs    = qs_base.filter(status=Chamado.Status.ABERTO)
    andamento_qs  = qs_base.filter(status=Chamado.Status.EM_ANDAMENTO)
    suspensos_qs  = qs_base.filter(status=Chamado.Status.SUSPENSO)
    concluidos_qs = qs_base.filter(status=Chamado.Status.CONCLUIDO)
    cancelados_qs = qs_base.filter(status=Chamado.Status.CANCELADO)

    allowed = {2, 5, 6, 10, 15, 20}
    def _ps(param, default):
        try:
            v = int(request.GET.get(param, default))
            return v if v in allowed else default
        except (TypeError, ValueError):
            return default

    ps_a, ps_and, ps_sus, ps_con, ps_can = (
        _ps("ps_a", 6), _ps("ps_and", 2), _ps("ps_sus", 2), _ps("ps_con", 2), _ps("ps_can", 2)
    )
    qs_preservada = _encode_filters_without_pages(request)

    context = {
        "form_tipo": NovaSolicitacaoTipoForm(user=request.user),

        "counts": {
            "abertos": abertos_qs.count(),
            "andamento": andamento_qs.count(),
            "suspensos": suspensos_qs.count(),
            "concluidos": concluidos_qs.count(),
            "cancelados": cancelados_qs.count(),
        },

        "abertos":    _paginar(abertos_qs,    ps_a,   "pg_a",   request),
        "andamento":  _paginar(andamento_qs,  ps_and, "pg_and", request),
        "suspensos":  _paginar(suspensos_qs,  ps_sus, "pg_sus", request),
        "concluidos": _paginar(concluidos_qs, ps_con, "pg_con", request),
        "cancelados": _paginar(cancelados_qs, ps_can, "pg_can", request),

        "ps_a": ps_a, "ps_and": ps_and, "ps_sus": ps_sus, "ps_con": ps_con, "ps_can": ps_can,
        "qs_a": qs_preservada, "qs_and": qs_preservada, "qs_sus": qs_preservada,
        "qs_con": qs_preservada, "qs_can": qs_preservada,

        "novos": {
            "abertos":    _updated_filter(abertos_qs,    _last_seen(request.user, "abertos")).count(),
            "andamento":  _updated_filter(andamento_qs,  _last_seen(request.user, "andamento")).count(),
            "suspensos":  _updated_filter(suspensos_qs,  _last_seen(request.user, "suspensos")).count(),
            "concluidos": _updated_filter(concluidos_qs, _last_seen(request.user, "concluidos")).count(),
            "cancelados": _updated_filter(cancelados_qs, _last_seen(request.user, "cancelados")).count(),
        },
    }
    return render(request, "solicitacoes/meus_chamados.html", context)


@login_required
@require_POST
def nova_solicitacao(request):
    """
    Abertura de chamado com proteção contra double-submit:
    - usa uma chave 'idem' enviada pelo formulário para idempotência
    - trava por 60s: se o mesmo usuário reenviar a mesma 'idem', ignora
    """
    # 1) Idempotência (opcional, mas recomendado): campo hidden 'idem'
    idem = (request.POST.get("idem") or "").strip()
    cache_key = None
    if idem:
        cache_key = f"nova_solic:{request.user.pk}:{idem}"
        # cache.add() -> False se a chave já existir (tentativa duplicada)
        if not cache.add(cache_key, "LOCK", timeout=60):
            messages.info(request, "Solicitação já enviada. Aguarde o processamento.")
            return redirect("solicitacoes:meus_chamados")

    tipo_id = request.POST.get("tipo")
    form_tmp = NovaSolicitacaoTipoForm(user=request.user)
    tipo = get_object_or_404(form_tmp.fields["tipo"].queryset, pk=tipo_id, ativo=True)

    # 2) Tudo-ou-nada
    with transaction.atomic():
        chamado = Chamado.objects.create(
            solicitante=request.user, tipo=tipo, status=Chamado.Status.ABERTO,
        )

        perguntas = tipo.perguntas.filter(ativa=True).order_by("ordem", "id")
        for p in perguntas:
            nome_base = f"pergunta_{p.id}"
            if p.tipo_campo == PerguntaTipoSolicitacao.TipoCampo.MULTIESCOLHA:
                valores = request.POST.getlist(nome_base)
                valor_texto = ";".join(v.strip() for v in valores if v.strip())
            elif p.tipo_campo == PerguntaTipoSolicitacao.TipoCampo.BOOLEANO:
                valor_texto = "true" if request.POST.get(nome_base) == "true" else "false"
            else:
                valor_texto = (request.POST.get(nome_base, "") or "").strip()

            valor_arquivo = None
            if p.tipo_campo == PerguntaTipoSolicitacao.TipoCampo.ARQUIVO and (nome_base + "_file") in request.FILES:
                valor_arquivo = request.FILES.get(nome_base + "_file")

            # Validação de obrigatórias (rollback implícito por transaction.atomic)
            if p.obrigatoria and p.tipo_campo != PerguntaTipoSolicitacao.TipoCampo.ARQUIVO and not valor_texto:
                # libera o cadeado para o usuário poder reenviar após erro
                if cache_key:
                    cache.delete(cache_key)
                messages.error(request, f'A pergunta "{p.texto}" é obrigatória.')
                return redirect("solicitacoes:meus_chamados")

            RespostaChamado.objects.create(
                chamado=chamado, pergunta=p, valor_texto=valor_texto, valor_arquivo=valor_arquivo
            )

    # (opcional) marca a chave como concluída por mais tempo
    if cache_key:
        cache.set(cache_key, f"DONE:{chamado.pk}", timeout=300)

    messages.success(request, f"Chamado #{chamado.id} aberto com sucesso!")
    return redirect("solicitacoes:meus_chamados")


@login_required
def form_campos_por_tipo(request, tipo_id):
    form_tmp = NovaSolicitacaoTipoForm(user=request.user)
    tipo = get_object_or_404(form_tmp.fields["tipo"].queryset, pk=tipo_id, ativo=True)
    perguntas = tipo.perguntas.filter(ativa=True).order_by("ordem", "id")
    return render(request, "solicitacoes/_campos_perguntas.html", {"tipo": tipo, "perguntas": perguntas})

@login_required
def reabrir_chamado(request, pk):
    ch = get_object_or_404(Chamado, pk=pk)

    if not _eh_admin(request.user):
        return HttpResponseForbidden("Sem permissão.")

    # mesma lógica do helper (resumida)
    my_id = request.user.id
    my_name = user_display(request.user).strip().lower()

    att_id = (
        getattr(ch, "atendente_id", None)
        or getattr(ch, "atendente_user_id", None)
        or getattr(getattr(ch, "atendente", None), "id", None)
        or getattr(getattr(ch, "atendente_user", None), "id", None)
    )
    att_name = (
        (getattr(ch, "atendente_nome", "") or "").strip().lower()
        or user_display(getattr(ch, "atendente", None)).strip().lower()
    )
    is_me = (att_id and att_id == my_id) or (att_name and att_name == my_name)

    if not is_me:
        messages.warning(request, "Apenas o atendente do chamado pode reabrir.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("solicitacoes:gerenciar_chamados"))

    if ch.status != Chamado.Status.SUSPENSO:
        messages.warning(request, "Somente chamados suspensos podem ser reabertos.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("solicitacoes:gerenciar_chamados"))

    ch.status = Chamado.Status.EM_ANDAMENTO
    ch.suspenso_em = None
    ch.save(update_fields=["status", "suspenso_em", "atualizado_em"])
    messages.success(request, "Chamado reaberto com sucesso.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("solicitacoes:gerenciar_chamados"))


@csrf_exempt
@login_required
@require_POST
def marcar_secao_vista(request):
    secao = (request.POST.get("secao") or "").strip()
    SECOES_OK = {"abertos", "andamento", "suspensos", "concluidos", "cancelados"}
    if secao not in SECOES_OK:
        return HttpResponseBadRequest("secao inválida")
    for tentativa in range(5):
        try:
            with transaction.atomic():
                SecaoVista.objects.update_or_create(
                    user=request.user, secao=secao, defaults={"last_seen": timezone.now()},
                )
            return JsonResponse({"ok": True})
        except OperationalError as e:
            if "locked" in str(e).lower() and tentativa < 4:
                time.sleep(0.1 * (tentativa + 1))
                continue
            raise
# ----------------- Gerenciar Chamados (Administrativo) -----------------
@admin_required
def gerenciar_chamados(request):
    # --- filtros ---
    tipo_ids = [int(x) for x in request.GET.getlist("tipo") if x.isdigit()]
    criado_de_raw = (request.GET.get("criado_de") or "").strip()
    criado_ate_raw = (request.GET.get("criado_ate") or "").strip()

    criado_de = None
    criado_ate = None
    try:
        if criado_de_raw:
            criado_de = datetime.strptime(criado_de_raw, "%Y-%m-%d").date()
    except ValueError:
        criado_de_raw = ""
    try:
        if criado_ate_raw:
            criado_ate = datetime.strptime(criado_ate_raw, "%Y-%m-%d").date()
    except ValueError:
        criado_ate_raw = ""

    qs_base = (
        Chamado.objects
        .select_related("tipo", "solicitante")
        .order_by("-criado_em")
    )

    if tipo_ids:
        qs_base = qs_base.filter(tipo_id__in=tipo_ids)
    if criado_de:
        qs_base = qs_base.filter(criado_em__date__gte=criado_de)
    if criado_ate:
        qs_base = qs_base.filter(criado_em__date__lte=criado_ate)

    # --- paginação ---
    allowed = {2, 5, 6, 10, 15, 20}
    def _ps(param, default):
        try:
            v = int(request.GET.get(param, default))
            return v if v in allowed else default
        except (TypeError, ValueError):
            return default

    ps_a   = _ps("ps_a", 6)
    ps_and = _ps("ps_and", 2)
    ps_sus = _ps("ps_sus", 2)
    ps_con = _ps("ps_con", 2)
    ps_can = _ps("ps_can", 2)

    abertos_page    = _paginar(qs_base.filter(status=Chamado.Status.ABERTO),       ps_a,   "pg_a",   request)
    andamento_page  = _paginar(qs_base.filter(status=Chamado.Status.EM_ANDAMENTO), ps_and, "pg_and", request)
    suspensos_page  = _paginar(qs_base.filter(status=Chamado.Status.SUSPENSO),     ps_sus, "pg_sus", request)
    concluidos_page = _paginar(qs_base.filter(status=Chamado.Status.CONCLUIDO),    ps_con, "pg_con", request)
    cancelados_page = _paginar(qs_base.filter(status=Chamado.Status.CANCELADO),    ps_can, "pg_can", request)

    # --- quem pode reabrir suspensos (já existia) ---
    can_reopen = _is_adminish(request.user)
    for c in suspensos_page.object_list:
        c.pode_reabrir = can_reopen

    # --- NOVO: quem pode gerenciar "Em andamento"
    me_name = user_display(request.user).strip().lower()
    is_root = bool(getattr(request.user, "is_superuser", False))
    for c in andamento_page.object_list:
        att_name = (getattr(c, "atendente_nome", "") or "").strip().lower()
        c.pode_gerenciar = is_root or (att_name and att_name == me_name)

    qs_preservada = _encode_filters_without_pages(request)

    context = {
        "tipos": TipoSolicitacao.objects.order_by("nome"),
        "tipo_ids": tipo_ids,
        "criado_de": criado_de_raw,
        "criado_ate": criado_ate_raw,

        "abertos":    abertos_page,
        "andamento":  andamento_page,
        "suspensos":  suspensos_page,
        "concluidos": concluidos_page,
        "cancelados": cancelados_page,

        "ps_a": ps_a, "ps_and": ps_and, "ps_sus": ps_sus, "ps_con": ps_con, "ps_can": ps_can,
        "qs_a": qs_preservada, "qs_and": qs_preservada, "qs_sus": qs_preservada,
        "qs_con": qs_preservada, "qs_can": qs_preservada,

        "motivos": ["Chamado não procede", "Chamado errado", "Chamado de teste", "Chamado perdido", "Outros"],
    }
    return render(request, "solicitacoes/gerenciar_chamados.html", context)



@login_required
def reabrir_chamado(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)

    # 🔒 qualquer admin-ish pode reabrir
    if not _is_adminish(request.user):
        return HttpResponseForbidden("Você não tem permissão para reabrir este chamado.")

    if chamado.status != Chamado.Status.SUSPENSO:
        messages.warning(request, "Somente chamados suspensos podem ser reabertos.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("solicitacoes:gerenciar_chamados"))

    chamado.status = Chamado.Status.EM_ANDAMENTO
    chamado.suspenso_em = None
    chamado.save(update_fields=["status", "suspenso_em", "atualizado_em"])
    messages.success(request, "Chamado reaberto com sucesso.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("solicitacoes:gerenciar_chamados"))




# views.py (trecho de assumir_chamado)
@admin_required
@require_POST
def assumir_chamado(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    u = request.user
    nome = user_display(u)[:120]

    fields = ["atendente_nome", "status", "suspenso_em", "atualizado_em"]
    chamado.atendente_nome = nome
    if hasattr(chamado, "atendente_user_id"):
        chamado.atendente_user = u
        fields.append("atendente_user")

    chamado.status = Chamado.Status.EM_ANDAMENTO
    chamado.suspenso_em = None
    chamado.save(update_fields=fields)

    messages.success(request, f"Chamado #{chamado.id} assumido por {nome} e movido para Em andamento.")
    return redirect("solicitacoes:gerenciar_chamados")


# ----------------- Tratativa -----------------

@login_required
@require_POST
def tratar_chamado(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    if not _pode_ver(request.user, chamado):
        return HttpResponseForbidden()

    next_url = request.POST.get("next") or reverse("solicitacoes:gerenciar_chamados")
    acao = (request.POST.get("acao") or "").strip()  # salvar|suspender|cancelar|concluir
    tratativa = (request.POST.get("tratativa_adm") or "").strip()
    motivo = (request.POST.get("motivo") or "").strip()
    anexo = request.FILES.get("anexo_adm")

    # 🔒 Finalizado: só superuser altera
    if _is_finalizado_status(chamado.status) and not request.user.is_superuser:
        messages.warning(request, "Chamado concluído/cancelado. Apenas superusuário pode alterar.")
        return redirect(reverse("solicitacoes:chamado_tratativa", args=[chamado.id]))

    # 🔒 Em andamento: somente o atendente que assumiu (ou superuser) pode alterar
    if (
        chamado.status == Chamado.Status.EM_ANDAMENTO
        and not request.user.is_superuser
        and not _is_assigned_to_me(request.user, chamado)
    ):
        nome = chamado.atendente_nome or "outro atendente"
        messages.warning(request, f"Este chamado está em andamento por {nome}.")
        return redirect(reverse("solicitacoes:chamado_tratativa", args=[chamado.id]))

    precisa_tratativa = acao in {"suspender", "cancelar", "concluir"}
    precisa_motivo = acao in {"suspender", "cancelar"}

    if precisa_tratativa and not tratativa:
        messages.error(request, "Informe a tratativa.")
        return redirect(reverse("solicitacoes:chamado_tratativa", args=[chamado.id]))
    if precisa_motivo and not motivo:
        messages.error(request, "Selecione um motivo para suspender/cancelar.")
        return redirect(reverse("solicitacoes:chamado_tratativa", args=[chamado.id]))

    updated_fields = []

    if tratativa:
        if precisa_motivo and motivo and "Motivo:" not in tratativa:
            chamado.tratativa_adm = f"{tratativa}\n\nMotivo: {motivo}"
        else:
            chamado.tratativa_adm = tratativa
        updated_fields.append("tratativa_adm")

    if anexo:
        chamado.anexo_adm = anexo
        updated_fields.append("anexo_adm")

    # Define atendente quando ainda não há
    if not chamado.atendente_nome:
        chamado.atendente_nome = user_display(request.user)[:120]
        updated_fields.append("atendente_nome")

    # Ações
    if acao == "salvar":
        if updated_fields:
            chamado.save(update_fields=updated_fields + ["atualizado_em"])
            messages.success(request, f"Chamado #{chamado.id} salvo.")
        else:
            messages.info(request, "Nenhuma alteração para salvar.")
        return redirect(reverse("solicitacoes:chamado_tratativa", args=[chamado.id]))

    if acao == "suspender":
        chamado.status = Chamado.Status.SUSPENSO
        chamado.suspenso_em = timezone.now()
        chamado.save(update_fields=updated_fields + ["status", "suspenso_em", "atualizado_em"])
        messages.success(request, f"Chamado #{chamado.id} suspenso.")
        return redirect(next_url)

    if acao == "cancelar":
        chamado.status = Chamado.Status.CANCELADO
        if not chamado.suspenso_em:
            chamado.suspenso_em = timezone.now()
            updated_fields.append("suspenso_em")
        chamado.save(update_fields=updated_fields + ["status", "atualizado_em"])
        messages.success(request, f"Chamado #{chamado.id} cancelado.")
        return redirect(next_url)

    if acao == "concluir":
        chamado.status = Chamado.Status.CONCLUIDO
        chamado.suspenso_em = None
        chamado.save(update_fields=updated_fields + ["status", "suspenso_em", "atualizado_em"])
        messages.success(request, f"Chamado #{chamado.id} concluído.")
        return redirect(next_url)

    return redirect(reverse("solicitacoes:chamado_tratativa", args=[chamado.id]))


@login_required
def chamado_tratativa(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    is_admin = _is_adminish(request.user)
    finalizado = _is_finalizado_status(chamado.status)
    assigned_to_me = _is_assigned_to_me(request.user, chamado)

    # 🔒 Bloqueia ações se: (finalizado e não superuser) OU
    # em andamento e NÃO sou o atendente (e não sou superuser)
    bloquear_acoes = (
        (finalizado and not request.user.is_superuser)
        or (
            chamado.status == Chamado.Status.EM_ANDAMENTO
            and not request.user.is_superuser
            and not assigned_to_me
        )
    )

    return render(
        request,
        "solicitacoes/chamado_tratativa.html",
        {
            "chamado": chamado,
            "is_admin": is_admin,
            "bloquear_acoes": bloquear_acoes,
            "assigned_to_me": assigned_to_me,  # opcional p/ exibir aviso no template
        },
    )


# ----------------- Parciais (Abertura/Conversa) -----------------

@login_required
def chamado_abertura_partial(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    if not _pode_ver(request.user, chamado):
        return HttpResponseForbidden()
    respostas = chamado.respostas.select_related("pergunta").all()
    return render(request, "solicitacoes/partials/_abertura.html", {"chamado": chamado, "respostas": respostas})

@login_required
def chamado_mensagens_partial(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    if not _pode_ver(request.user, chamado):
        return HttpResponseForbidden()

    qs = ChamadoMensagem.objects.filter(chamado=chamado).select_related("autor").order_by("criado_em")
    if not _is_adminish(request.user):
        vis_publica = getattr(ChamadoMensagem, "PUBLICA", "publica")
        qs = qs.filter(visibilidade=vis_publica)

    return render(request, "solicitacoes/partials/_conversa.html", {"chamado": chamado, "mensagens": qs})

@login_required
def chamado_enviar_mensagem(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    if not _pode_ver(request.user, chamado):
        return HttpResponseForbidden()

    if request.method == "POST":
        files = request.FILES.copy()
        if "anexo" not in files and "arquivo" in files:
            files["anexo"] = files["arquivo"]

        form = ChamadoMensagemForm(request.POST, files)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.chamado = chamado
            msg.autor = request.user
            if not _is_adminish(request.user):
                msg.visibilidade = getattr(ChamadoMensagem, "PUBLICA", "publica")
            elif not getattr(msg, "visibilidade", None):
                msg.visibilidade = getattr(ChamadoMensagem, "PUBLICA", "publica")
            msg.save()
        else:
            html = render(
                request, "solicitacoes/partials/_conversa.html",
                {"chamado": chamado, "mensagens": ChamadoMensagem.objects.filter(chamado=chamado).order_by("criado_em")}
            ).content.decode("utf-8")
            from django.utils.html import escape
            erros = escape(form.errors.as_json())
            html = html.replace(
                'id="conversa-erros" class="text-danger small mt-2 d-none"',
                'id="conversa-erros" class="text-danger small mt-2"'
            ).replace(
                '</form>',
                f'<div class="text-danger small mt-2">{erros}</div></form>'
            )
            return HttpResponse(html)

        return chamado_mensagens_partial(request, pk)

    return redirect("solicitacoes:chamado_tratativa", pk=pk)

# ----------------- “Abertos” como parcial (usado por HTMX/refresh) -----------------

@admin_required
def frag_abertos(request):
    tipo_ids = [int(x) for x in request.GET.getlist("tipo") if x.isdigit()]
    criado_de_raw  = (request.GET.get("criado_de") or "").strip()
    criado_ate_raw = (request.GET.get("criado_ate") or "").strip()

    criado_de = None
    criado_ate = None
    try:
        if criado_de_raw:
            criado_de = datetime.strptime(criado_de_raw, "%Y-%m-%d").date()
    except ValueError:
        criado_de_raw = ""
    try:
        if criado_ate_raw:
            criado_ate = datetime.strptime(criado_ate_raw, "%Y-%m-%d").date()
    except ValueError:
        criado_ate_raw = ""

    qs_base = Chamado.objects.select_related("tipo", "solicitante").order_by("-criado_em")
    if tipo_ids:
        qs_base = qs_base.filter(tipo_id__in=tipo_ids)
    if criado_de:
        qs_base = qs_base.filter(criado_em__date__gte=criado_de)
    if criado_ate:
        qs_base = qs_base.filter(criado_em__date__lte=criado_ate)

    allowed = {2, 5, 6, 10, 15, 20}
    def _ps(param, default):
        try:
            v = int(request.GET.get(param, default))
            return v if v in allowed else default
        except (TypeError, ValueError):
            return default
    ps_a = _ps("ps_a", 6)

    abertos_page = _paginar(qs_base.filter(status=Chamado.Status.ABERTO), ps_a, "pg_a", request)

    return render(
        request, "solicitacoes/partials/_sessao_abertos.html",
        {
            "tipos": TipoSolicitacao.objects.order_by("nome"),
            "tipo_ids": tipo_ids,
            "criado_de": criado_de_raw,
            "criado_ate": criado_ate_raw,
            "abertos": abertos_page,
            "ps_a": ps_a,
            "qs_a": _encode_filters_without_pages(request),
        },
    )

# ----------------- Vistos / Notificações -----------------

@csrf_exempt
@login_required
@require_POST
def marcar_conversa_vista(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    if not _pode_ver(request.user, chamado):
        return HttpResponseForbidden()
    ChamadoVista.objects.update_or_create(
        user=request.user, chamado=chamado, defaults={"last_seen": timezone.now()}
    )
    return JsonResponse({"ok": True})

@login_required
def api_novas_mensagens(request):
    """
    GET /solicitacoes/notificacoes/novas/?ids=9,8,7
    Retorna { <id>: true } quando há mensagem pública mais recente que o last_seen do usuário naquele chamado.
    """
    ids_param = (request.GET.get("ids") or "").strip()
    if not ids_param:
        return JsonResponse({})

    try:
        ids = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]
    except ValueError:
        return HttpResponseBadRequest("ids inválidos")
    if not ids:
        return JsonResponse({})

    vistas = dict(
        ChamadoVista.objects.filter(user=request.user, chamado_id__in=ids)
        .values_list("chamado_id", "last_seen")
    )

    rows = (
        ChamadoMensagem.objects.filter(chamado_id__in=ids, visibilidade=ChamadoMensagem.PUBLICA)
        .exclude(autor=request.user)
        .values("chamado_id")
        .annotate(last=Max("criado_em"))
    )

    out = {}
    for r in rows:
        cid = r["chamado_id"]
        last_msg  = r["last"]
        last_seen = vistas.get(cid)
        if not last_seen or (last_msg and last_msg > last_seen):
            out[cid] = True

    return JsonResponse(out)

@csrf_exempt
@login_required
def atendimento_seen(request):
    print("### atendimento_seen HIT:", request.method, "RAW_PATH=", request.get_full_path())
    # resto da função...
    raw = request.POST.get('ids') or request.GET.get('ids')
    if not raw:
        ids = request.POST.getlist('ids[]')
    else:
        ids = [x for x in re.split(r'[,\s;]+', raw) if x]

    ids = [int(x) for x in ids if str(x).isdigit()]
    if not ids:
        return JsonResponse({"ok": True, "count": 0})

    now = timezone.now()
    for cid in ids:
        ChamadoVista.objects.update_or_create(
            user=request.user, chamado_id=cid, defaults={"last_seen": now}
        )
    return JsonResponse({"ok": True, "count": len(ids)})

@login_required
@require_POST
def marcar_chamados_vistos(request):
    raw = (request.POST.get("ids") or "").strip()
    if not raw:
        return JsonResponse({"ok": True})

    ids = []
    for p in raw.split(","):
        p = p.strip()
        if not p:
            continue
        try:
            ids.append(int(p))
        except ValueError:
            pass
    if not ids:
        return JsonResponse({"ok": True})

    agora = timezone.now()
    for tentativa in range(5):
        try:
            with transaction.atomic():
                for cid in ids:
                    ChamadoVista.objects.update_or_create(
                        user=request.user, chamado_id=cid, defaults={"last_seen": agora},
                    )
            return JsonResponse({"ok": True})
        except OperationalError as e:
            if "locked" in str(e).lower() and tentativa < 4:
                time.sleep(0.1 * (tentativa + 1))
                continue
            raise





# --- VIEW INLINE (CSRF-EXEMPT) para marcar "visto" ---
@csrf_exempt
@login_required
def _seen_alias(request):
    raw = request.POST.get('ids') or request.GET.get('ids')
    if not raw:
        ids = request.POST.getlist('ids[]')
    else:
        # ✅ usa re.split, não _re.split
        ids = [x for x in re.split(r'[,\s;]+', raw) if x]

    ids = [int(x) for x in ids if str(x).isdigit()]
    if not ids:
        return JsonResponse({"ok": True, "count": 0})

    now = timezone.now()
    for cid in ids:
        ChamadoVista.objects.update_or_create(
            user=request.user, chamado_id=cid, defaults={"last_seen": now}
        )
    return JsonResponse({"ok": True, "count": len(ids)})







# views do dashboard solicitações
# solicitacoes/views.py



@login_required
def dashboard(request):
    """
    Renderiza a página do dashboard.
    O gráfico e cards carregam dados via /solicitacoes/dashboard/data/
    """
    return render(request, "solicitacoes/dashboard.html")

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q

from .models import Chamado


def _count_status(qs, *member_names: str) -> int:
    """
    Conta itens por status, aceitando múltiplos nomes de membro do Enum/Choices.
    Ex.: _count_status(qs, "ANDAMENTO", "EM_ANDAMENTO")
    """
    vals = []
    for name in member_names:
        val = getattr(Chamado.Status, name, None)
        if val is not None:
            vals.append(val)
    return qs.filter(status__in=vals).count() if vals else 0




@login_required
def dashboard_data(request):
    user = request.user

    # aplica a regra de visibilidade (admin/superuser = tudo,
    # gestor = time + próprios, colaborador = próprios)
    base_qs = Chamado.objects.select_related("tipo", "solicitante")
    qs = visible_chamados_for(user, base_qs)

    # métricas por status
    abertos      = qs.filter(status=Chamado.Status.ABERTO).count()
    andamento    = qs.filter(status=Chamado.Status.EM_ANDAMENTO).count()
    suspensos    = qs.filter(status=Chamado.Status.SUSPENSO).count()
    concluidos   = qs.filter(status=Chamado.Status.CONCLUIDO).count()
    cancelados   = qs.filter(status=Chamado.Status.CANCELADO).count()
    total        = qs.count()

    # top 5 tipos
    top_tipos_qs = (
        qs.values("tipo__nome")
          .annotate(qtd=Count("id"))
          .order_by("-qtd")[:5]
    )
    data = {
        "cards": {
            "total": total,
            "abertos": abertos,
            "andamento": andamento,
            "suspensos": suspensos,
            "concluidos": concluidos,
            "cancelados": cancelados,
        },
        "top_tipos": {
            "labels": [(row["tipo__nome"] or "Sem tipo") for row in top_tipos_qs],
            "values": [row["qtd"] for row in top_tipos_qs],
        },
    }
    return JsonResponse(data)






@login_required
def dashboard_table(request):
    user = request.user

    base_qs = Chamado.objects.select_related("tipo", "solicitante")
    qs = visible_chamados_for(user, base_qs)

    # filtros de busca
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(solicitante__nome_completo__icontains=q) |
            Q(solicitante__cpf__icontains=q) |
            Q(solicitante__email__icontains=q)
        )

    tipo = (request.GET.get("tipo") or "").strip()
    if tipo:
        qs = qs.filter(tipo_id=tipo)

    de = (request.GET.get("de") or "").strip()
    ate = (request.GET.get("ate") or "").strip()
    if de:
        qs = qs.filter(criado_em__date__gte=de)
    if ate:
        qs = qs.filter(criado_em__date__lte=ate)

    qs = qs.order_by("-criado_em")

    # paginação segura
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, int(request.GET.get("page_size", 50)))
    except (TypeError, ValueError):
        page_size = 50

    start, end = (page - 1) * page_size, page * page_size

    total = qs.count()
    rows = []
    for c in qs[start:end]:
        try:
            link = reverse("solicitacoes:chamado_tratativa", args=[c.pk])
        except Exception:
            link = ""

        s = getattr(c, "solicitante", None)
        solicitante = "-"
        if s:
            solicitante = getattr(s, "nome_completo", None) or getattr(s, "cpf", None) or str(s)

        rows.append({
            "id": c.pk,
            "data": c.criado_em.strftime("%d/%m/%Y %H:%M"),
            "solicitante": solicitante,
            "tipo": getattr(getattr(c, "tipo", None), "nome", "-"),
            "status": c.get_status_display(),
            "link": link,
        })

    return JsonResponse({"rows": rows, "total": total})





@login_required
@require_GET
def chamado_modal(request, pk: int):
    from .models import Chamado  # ajuste se seu import for diferente

    try:
        ch = (
            Chamado.objects
            .select_related("tipo", "solicitante")  # 'atendente' não existe: removido
            .get(pk=pk)
        )
    except Chamado.DoesNotExist:
        raise Http404("Chamado não encontrado")

    # ---- Normaliza Perguntas & Respostas em uma lista "qa" ----
    qa = []

    def _get(obj, *names):
        """Tenta pegar o primeiro atributo existente/não vazio de obj."""
        for n in names:
            if hasattr(obj, n):
                val = getattr(obj, n)
                if callable(val):
                    try:
                        val = val()
                    except Exception:
                        pass
                if val not in (None, ""):
                    return val
        return None

    # tenta detectar o related das respostas (um dos nomes abaixo)
    related_names = [
        "respostas",                # se você nomeou assim
        "respostas_chamado",        # variação comum
        "respostachamado_set",      # nome reverso padrão do Django
        "respostaset",              # só por precaução
    ]

    resp_qs = None
    for rel in related_names:
        if hasattr(ch, rel):
            try:
                resp_qs = getattr(ch, rel).all()
            except Exception:
                resp_qs = None
            if resp_qs is not None:
                break

    if resp_qs:
        for r in resp_qs:
            # Pega o objeto da pergunta em diferentes nomes possíveis
            p = _get(r,
                     "pergunta", "pergunta_tipo", "pergunta_tiposolicitacao",
                     "pergunta_tipo_solicitacao", "pergunta_obj")

            # Texto da pergunta (tentando vários campos típicos)
            q_txt = _get(p, "titulo", "texto", "label", "nome", "descricao", "descricao_curta") or "Pergunta"

            # Valor/resposta em diferentes campos
            a_txt = _get(r, "valor", "resposta", "texto", "valor_texto", "conteudo") or "—"

            qa.append({"q": q_txt, "a": a_txt})

    html = render_to_string(
        "solicitacoes/_chamado_modal.html",
        {"c": ch, "qa": qa},  # <-- envia a lista pronta
        request=request,
    )
    return JsonResponse({"html": html})







def _is_gestor_or_superuser(u):
    return (u.is_authenticated and (u.is_superuser or getattr(u, "perfil", None) == "GESTOR"))

admin_report_required = user_passes_test(_is_gestor_or_superuser)

@admin_report_required
def relatorio_solicitacoes(request):
    # ----- Base Query
    qs = (
        Chamado.objects
        .select_related("tipo", "solicitante")
        .order_by("-criado_em")
    )

    # ----- Filtros
    q = (request.GET.get("q") or "").strip()            # ID ou solicitante
    tipo = (request.GET.get("tipo") or "").strip()      # tipo_id
    status = (request.GET.get("status") or "").strip()  # código do status
    de = (request.GET.get("de") or "").strip()          # YYYY-MM-DD
    ate = (request.GET.get("ate") or "").strip()        # YYYY-MM-DD

    # q: número -> ID; texto -> campos do solicitante
    if q:
        if q.isdigit():
            qs = qs.filter(id=int(q))
        else:
            UserModel = get_user_model()
            user_fields = {f.name for f in UserModel._meta.get_fields() if hasattr(f, "name")}
            qf = (
                Q(solicitante__username__icontains=q) |
                Q(solicitante__first_name__icontains=q) |
                Q(solicitante__last_name__icontains=q)
            )
            if "nome_completo" in user_fields:
                qf |= Q(solicitante__nome_completo__icontains=q)
            qs = qs.filter(qf)

    if tipo:
        qs = qs.filter(tipo_id=tipo)

    if status:
        qs = qs.filter(status=status)

    # período por data de criação
    def _parse_d(dstr):
        try:
            return date.fromisoformat(dstr)
        except Exception:
            return None

    d_de = _parse_d(de)
    d_ate = _parse_d(ate)
    if d_de:
        qs = qs.filter(criado_em__date__gte=d_de)
    if d_ate:
        qs = qs.filter(criado_em__date__lte=d_ate)

    # ----- Exportar Excel (respeitando filtros)
    export = (request.GET.get("export") or "").lower()
    can_export = _is_gestor_or_superuser(request.user)
    if export == "xlsx" and can_export:
        try:
            from openpyxl import Workbook
        except Exception:
            return HttpResponseBadRequest("Exportação indisponível: instale 'openpyxl'.")

        wb = Workbook()
        ws = wb.active
        ws.title = "Solicitações"

        # Cabeçalho
        ws.append(["ID", "Solicitante", "Tipo", "Status", "Criado em"])

        # Linhas (sem paginação)
        for c in qs.iterator():
            solicitante_str = str(c.solicitante) if c.solicitante else ""
            tipo_str = c.tipo.nome if getattr(c, "tipo", None) else ""
            status_str = c.get_status_display() if hasattr(c, "get_status_display") else c.status
            criado_str = c.criado_em.strftime("%d/%m/%Y %H:%M") if getattr(c, "criado_em", None) else ""
            ws.append([c.id, solicitante_str, tipo_str, status_str, criado_str])

        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        resp = HttpResponse(
            bio.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="relatorio-solicitacoes.xlsx"'
        return resp

    # ----- Paginação
    paginator = Paginator(qs, 50)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    # Opções do select de tipo
    tipos = (
        Chamado.objects
        .select_related("tipo")
        .values("tipo_id", "tipo__nome")
        .distinct()
        .order_by("tipo__nome")
    )

    # Status choices
    status_choices = getattr(Chamado.Status, "choices", [])

    # Querystring sem 'page' p/ paginação e export
    params = request.GET.copy()
    params.pop("page", None)
    qs_keep = params.urlencode()

    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "tipos": tipos,
        "status_choices": status_choices,
        "filters": {"q": q, "tipo": tipo, "status": status, "de": de, "ate": ate},
        "can_export": can_export,
        "qs_keep": qs_keep,
    }
    return render(request, "solicitacoes/relatorio.html", ctx)




# ... seus outros imports

@login_required
@admin_report_required
@require_GET
def relatorio_chamado_modal(request, pk: int):
    chamado = get_object_or_404(
        Chamado.objects.select_related("tipo", "solicitante"),
        pk=pk,
    )

    # --- Respostas de abertura
    respostas_qs = list(
        RespostaChamado.objects.select_related("pergunta")
        .filter(chamado=chamado)
        .order_by("id")
    )

    def _as_text_generic(resp):
        """
        Procura em campos concretos (Char/Text/JSON) e retorna a
        primeira string não vazia. Ignora FKs/arquivos.
        NUNCA cai no __str__ do model (evita repetir a pergunta).
        """
        # Campos que não são conteúdo de resposta
        blacklist = {
            "id", "pk",
            "chamado", "chamado_id",
            "pergunta", "pergunta_id",
            "criado_em", "atualizado_em",
            "created", "updated", "modificado_em",
            "autor", "autor_id",
            "arquivo", "arquivos", "file", "files", "anexo", "anexos",
        }

        # Percorre apenas campos "concretos"
        for f in getattr(resp._meta, "fields", []):
            name = getattr(f, "name", "")
            if not name or name in blacklist:
                continue

            # ignora relações
            if getattr(f, "is_relation", False):
                continue

            try:
                v = getattr(resp, name)
            except Exception:
                continue

            if v in (None, ""):
                continue

            # ignora arquivo/FieldFile
            if hasattr(v, "url") or hasattr(v, "file"):
                continue

            # coleções/JSON
            if isinstance(v, (list, tuple)):
                s = "\n".join(str(x) for x in v).strip()
                if s:
                    return s
            elif isinstance(v, dict):
                s = "\n".join(
                    f"{k}: {vv}"
                    for k, vv in v.items()
                    if str(k).lower() not in ("anexo", "arquivo", "arquivos", "file", "files")
                ).strip()
                if s:
                    return s
            else:
                s = str(v).strip()
                if s:
                    return s

        # nada encontrado
        return ""

    # Mapa pergunta_id -> lista de textos
    respostas_map = {}
    for r in respostas_qs:
        pid = getattr(r, "pergunta_id", None) or (getattr(r, "pergunta", None).pk if getattr(r, "pergunta", None) else None)
        if not pid:
            continue
        txt = _as_text_generic(r)
        if txt:
            respostas_map.setdefault(pid, []).append(txt)

    # --- Perguntas do tipo
    perguntas = list(
        PerguntaTipoSolicitacao.objects.filter(tipo=chamado.tipo).order_by("id")
    )

    qa_rows = []
    for p in perguntas:
        label = getattr(p, "nome", None) or getattr(p, "titulo", None) or str(p)
        lcl = (label or "").lower()

        # oculta perguntas de anexo
        if "anexo" in lcl:
            continue

        pid = getattr(p, "id", None)
        val = "\n".join(respostas_map.get(pid, [])) if pid else ""

        # fallbacks do próprio Chamado
        if not val:
            if "nome" in lcl and ("solicita" in lcl or "daria" in lcl):
                for attr in ("titulo", "nome", "assunto", "nome_solicitacao"):
                    v = getattr(chamado, attr, None)
                    if v and str(v).strip():
                        val = str(v).strip()
                        break
            if not val and ("detal" in lcl or "descr" in lcl):
                for attr in ("detalhamento", "descricao", "descricao_solicitacao", "observacoes", "observacao"):
                    v = getattr(chamado, attr, None)
                    if v and str(v).strip():
                        val = str(v).strip()
                        break

        qa_rows.append({"label": label, "value": val})

    # Se não houver perguntas, tenta exibir título/detalhamento do Chamado
    if not qa_rows:
        def _maybe(label, *attrs):
            for a in attrs:
                v = getattr(chamado, a, None)
                if v and str(v).strip():
                    qa_rows.append({"label": label, "value": str(v).strip()})
                    return
        _maybe("Título / Nome da Solicitação", "titulo", "nome", "assunto", "nome_solicitacao")
        _maybe("Detalhamento da Solicitação", "detalhamento", "descricao", "descricao_solicitacao")

    # --- Mensagens
    mensagens = (
        ChamadoMensagem.objects.filter(chamado=chamado)
        .select_related("autor")
        .order_by("criado_em")
    )

    ctx = {
        "chamado": chamado,
        "qa_rows": qa_rows,
        "mensagens": mensagens,
    }
    return render(request, "solicitacoes/_relatorio_modal.html", ctx)




# util opcional para limpar arquivos de FileField/ImageField
def _delete_files_of(obj):
    from django.db.models.fields.files import FileField
    for f in obj._meta.get_fields():
        if isinstance(getattr(f, "field", None), FileField) or isinstance(f, FileField):
            try:
                file = getattr(obj, f.name)
                if file and hasattr(file, "delete"):
                    file.delete(save=False)
            except Exception:
                pass

def _delete_related_files(chamado):
    # percorre relacionamentos one-to-many/one-to-one e apaga arquivos se houver
    for rel in chamado._meta.get_fields():
        if rel.auto_created and (rel.one_to_many or rel.one_to_one):
            accessor = getattr(chamado, rel.get_accessor_name(), None)
            if accessor is None:
                continue
            try:
                if rel.one_to_one:
                    obj = accessor
                    if obj:
                        _delete_files_of(obj)
                else:
                    for obj in accessor.all():
                        _delete_files_of(obj)
            except Exception:
                pass
    # por via das dúvidas, também no próprio chamado
    _delete_files_of(chamado)

@login_required
def relatorio_chamado_delete(request, pk: int):
    """
    GET  -> retorna HTML de confirmação (carregado no modal via HTMX).
    POST -> executa a exclusão (apenas superusuário).
    """
    chamado = get_object_or_404(Chamado.objects.select_related("tipo", "solicitante"), pk=pk)

    if request.method == "GET":
        if not request.user.is_superuser:
            return HttpResponseForbidden("Ação permitida apenas para superusuário.")
        ctx = {"chamado": chamado}
        return render(request, "solicitacoes/_relatorio_delete_confirm.html", ctx)

    # POST
    if not request.user.is_superuser:
        return HttpResponseForbidden("Ação permitida apenas para superusuário.")

    with transaction.atomic():
        # remover arquivos em disco (se seus modelos tiverem FileField/ImageField)
        _delete_related_files(chamado)
        chamado.delete()

    # resposta vazia, só disparando evento p/ remover a linha e fechar o modal
    headers = {
        "HX-Trigger": json.dumps({"chamadoDeleted": {"id": pk}}),
    }
    return HttpResponse(status=204, headers=headers)
