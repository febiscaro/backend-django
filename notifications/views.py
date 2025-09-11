# notifications/views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .models import Notification

def _user_email(request):
    return (request.user.email or "").strip()

@login_required
def list_notifications(request):
    email = _user_email(request)
    qs = Notification.objects.filter(to_email__iexact=email).order_by("-created_at") if email else Notification.objects.none()
    return render(request, "notifications/list.html", {"notifications": qs})

@login_required
def count_unread(request):
    email = _user_email(request)
    count = Notification.objects.filter(to_email__iexact=email, channel="web").count() if email else 0
    return JsonResponse({"count": count})

@login_required
def dropdown(request):
    email = _user_email(request)
    qs = Notification.objects.filter(to_email__iexact=email, channel="web").order_by("-created_at")[:10] if email else Notification.objects.none()
    return render(request, "notifications/_dropdown.html", {"notifications": qs})

@login_required
@require_http_methods(["GET", "POST"])
def mark_read(request, pk: int):
    email = _user_email(request)
    Notification.objects.filter(pk=pk, to_email__iexact=email).delete()
    if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(request.META.get("HTTP_REFERER", "/"))
