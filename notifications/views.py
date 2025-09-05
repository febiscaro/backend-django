# notifications/views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect    # render + redirect
from django.views.decorators.http import require_http_methods

from .models import Notification


@login_required
def list_notifications(request):
    """Lista todas as notificações do usuário logado"""
    email = (request.user.email or "").strip()
    qs = Notification.objects.none()
    if email:
        qs = Notification.objects.filter(
            to_email__iexact=email
        ).order_by("-created_at")
    return render(request, "notifications/list.html", {"notifications": qs})


def _user_notifications_qs(request):
    """Helper para pegar o queryset de notificações do usuário"""
    email = (request.user.email or "").strip()
    if not email:
        return Notification.objects.none()

    # 👉 Unifique aqui o filtro
    # Tudo (email + web):
    return Notification.objects.filter(to_email__iexact=email)

    # Só “web” (se o signals criar channel='web'):
    # return Notification.objects.filter(to_email__iexact=email, channel="web")


@login_required
def count_unread(request):
    """Conta notificações do usuário (não filtramos read_at, pois estamos apagando ao marcar lida)"""
    qs = _user_notifications_qs(request)
    return JsonResponse({"count": qs.count()})


@login_required
def dropdown(request):
    """Dropdown com últimas 10 notificações do usuário"""
    email = (request.user.email or "").strip()
    qs = Notification.objects.none()
    if email:
        qs = Notification.objects.filter(
            to_email__iexact=email
        ).order_by("-created_at")[:10]
        # se quiser só “web”: .filter(to_email__iexact=email, channel="web")
    return render(request, "notifications/_dropdown.html", {"notifications": qs})


@login_required
@require_http_methods(["GET", "POST"])
def mark_read(request, pk: int):
    """Marcar uma notificação como lida (no nosso caso: deletar)"""
    email = (request.user.email or "").strip()
    Notification.objects.filter(pk=pk, to_email__iexact=email).delete()

    # Se for ajax/htmx, devolve JSON
    if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})

    # Senão, redireciona para onde estava
    return redirect(request.META.get("HTTP_REFERER", "/"))
