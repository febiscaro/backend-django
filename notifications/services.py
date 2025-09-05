# notifications/services.py
from typing import Optional, Dict, Iterable
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import models
from django.template.loader import render_to_string
from django.utils import timezone
from .models import Notification, NotificationOptOut

User = get_user_model()

def is_opted_out(email: str, kind: str) -> bool:
    return NotificationOptOut.objects.filter(email=email).filter(
        models.Q(kind="") | models.Q(kind=kind)
    ).exists()

def render_email(kind: str, context: Dict) -> Dict[str, str]:
    base = f"notifications/emails/{kind}"
    subject = render_to_string(f"{base}/subject.txt", context).strip()
    body_txt = render_to_string(f"{base}/body.txt", context)
    try:
        body_html = render_to_string(f"{base}/body.html", context)
    except Exception:
        body_html = ""
    return {"subject": subject, "body_text": body_txt, "body_html": body_html}

def _match_user(email: str):
    if not email:
        return None
    try:
        return User.objects.filter(email__iexact=email).first()
    except Exception:
        return None

def send_email(
    kind: str,
    to_email: str,
    context: Dict,
    ref: Optional[Dict] = None,
    save_log: bool = True
) -> Optional[Notification]:

    if not to_email:
        return None
    if is_opted_out(to_email, kind):
        return None

    payload = render_email(kind, context)

    # --- Monta kwargs para o Notification respeitando o schema atual do model ---
    notif_kwargs = dict(
        kind=kind,
        to_email=to_email,
        subject=payload["subject"],
        body_text=payload["body_text"],
        body_html=payload["body_html"],
        ref_app=(ref or {}).get("app", ""),
        ref_model=(ref or {}).get("model", ""),
        ref_pk=str((ref or {}).get("pk", "")),
    )

    # Só passa to_user se o model tiver esse campo (evita TypeError)
    maybe_user = _match_user(to_email)
    if hasattr(Notification, "to_user") and maybe_user:
        notif_kwargs["to_user"] = maybe_user

    notif: Optional[Notification] = Notification(**notif_kwargs) if save_log else None

    try:
        conn = get_connection()
        email = EmailMultiAlternatives(
            subject=payload["subject"],
            body=payload["body_text"],
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to_email],
            connection=conn,
        )
        if payload["body_html"]:
            email.attach_alternative(payload["body_html"], "text/html")
        email.send()

        if notif:
            notif.is_sent = True
            notif.sent_at = timezone.now()
            notif.save()
    except Exception as e:
        if notif:
            notif.error = str(e)[:1000]
            notif.save()
        else:
            # quando não salva log, propaga para não silenciar erros de envio
            raise
    return notif


def send_simple_email(
    subject: str,
    body: str,
    to_list: Iterable[str],
    kind: str = "generic",
    ref: Optional[Dict] = None
):
    for email in to_list or []:
        send_email(kind=kind, to_email=email, context={"subject": subject, "body": body}, ref=ref)
