# -*- coding: utf-8 -*-
import re
import time
from datetime import datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, Paginator
from django.db import OperationalError, transaction
from django.db.models import Max
from django.forms import inlineformset_factory
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import (
    ChamadoMensagemForm,
    NovaSolicitacaoTipoForm,
    PerguntaTipoSolicitacaoForm,
    TipoSolicitacaoForm,
)
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

# ----------------- helpers -----------------

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

@login_required
def meus_chamados(request):
    # ADMIN não deve acessar "Meus Chamados" (apenas superuser pode ver tudo)
    if not request.user.is_superuser and str(getattr(request.user, "perfil", "") or "").upper() == "ADMIN":
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

    ps_a, ps_and, ps_sus, ps_con, ps_can = _ps("ps_a", 6), _ps("ps_and", 2), _ps("ps_sus", 2), _ps("ps_con", 2), _ps("ps_can", 2)
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
    tipo_id = request.POST.get("tipo")
    form_tmp = NovaSolicitacaoTipoForm(user=request.user)
    tipo = get_object_or_404(form_tmp.fields["tipo"].queryset, pk=tipo_id, ativo=True)

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

        if p.obrigatoria and p.tipo_campo != PerguntaTipoSolicitacao.TipoCampo.ARQUIVO and not valor_texto:
            chamado.delete()
            messages.error(request, f'A pergunta "{p.texto}" é obrigatória.')
            return redirect("solicitacoes:meus_chamados")

        RespostaChamado.objects.create(
            chamado=chamado, pergunta=p, valor_texto=valor_texto, valor_arquivo=valor_arquivo
        )

    messages.success(request, f"Chamado #{chamado.id} aberto com sucesso!")
    return redirect("solicitacoes:meus_chamados")

@login_required
def form_campos_por_tipo(request, tipo_id):
    form_tmp = NovaSolicitacaoTipoForm(user=request.user)
    tipo = get_object_or_404(form_tmp.fields["tipo"].queryset, pk=tipo_id, ativo=True)
    perguntas = tipo.perguntas.filter(ativa=True).order_by("ordem", "id")
    return render(request, "solicitacoes/_campos_perguntas.html", {"tipo": tipo, "perguntas": perguntas})

@login_required
@require_POST
def reabrir_chamado(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk, solicitante=request.user)
    if chamado.status != Chamado.Status.SUSPENSO:
        messages.error(request, "Este chamado não está suspenso.")
        return redirect("solicitacoes:meus_chamados")
    chamado.reabrir()
    chamado.save(update_fields=["status", "suspenso_em", "atualizado_em"])
    messages.success(request, f"Chamado #{chamado.id} reaberto com sucesso!")
    return redirect("solicitacoes:meus_chamados")

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

    ps_a, ps_and, ps_sus, ps_con, ps_can = _ps("ps_a", 6), _ps("ps_and", 2), _ps("ps_sus", 2), _ps("ps_con", 2), _ps("ps_can", 2)

    context = {
        "tipos": TipoSolicitacao.objects.order_by("nome"),
        "tipo_ids": tipo_ids,
        "criado_de": criado_de_raw,
        "criado_ate": criado_ate_raw,

        "abertos":    _paginar(qs_base.filter(status=Chamado.Status.ABERTO),       ps_a,   "pg_a",   request),
        "andamento":  _paginar(qs_base.filter(status=Chamado.Status.EM_ANDAMENTO), ps_and, "pg_and", request),
        "suspensos":  _paginar(qs_base.filter(status=Chamado.Status.SUSPENSO),     ps_sus, "pg_sus", request),
        "concluidos": _paginar(qs_base.filter(status=Chamado.Status.CONCLUIDO),    ps_con, "pg_con", request),
        "cancelados": _paginar(qs_base.filter(status=Chamado.Status.CANCELADO),    ps_can, "pg_can", request),

        "ps_a": ps_a, "ps_and": ps_and, "ps_sus": ps_sus, "ps_con": ps_con, "ps_can": ps_can,
        "qs_a":   _encode_filters_without_pages(request),
        "qs_and": _encode_filters_without_pages(request),
        "qs_sus": _encode_filters_without_pages(request),
        "qs_con": _encode_filters_without_pages(request),
        "qs_can": _encode_filters_without_pages(request),

        "motivos": ["Chamado não procede", "Chamado errado", "Chamado de teste", "Chamado perdido", "Outros"],
    }
    return render(request, "solicitacoes/gerenciar_chamados.html", context)

@admin_required
@require_POST
def assumir_chamado(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk)
    u = request.user
    nome = user_display(u)[:120]
    chamado.atendente_nome = nome
    chamado.status = Chamado.Status.EM_ANDAMENTO
    chamado.suspenso_em = None
    chamado.save(update_fields=["atendente_nome", "status", "suspenso_em", "atualizado_em"])
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

    # 🔒 bloqueio para não-superuser quando já finalizado
    if _is_finalizado_status(chamado.status) and not request.user.is_superuser:
        messages.warning(request, "Chamado concluído/cancelado. Apenas superusuário pode alterar.")
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
    bloquear_acoes = finalizado and (not request.user.is_superuser)

    return render(
        request,
        "solicitacoes/chamado_tratativa.html",
        {
            "chamado": chamado,
            "is_admin": is_admin,
            "bloquear_acoes": bloquear_acoes,
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
