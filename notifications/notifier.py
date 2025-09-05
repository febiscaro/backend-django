from typing import Optional
from django.contrib.auth import get_user_model
from .services import send_email

User = get_user_model()

def notify_ticket_created(chamado, destinatario: Optional[str] = None):
    email = destinatario or getattr(chamado.solicitante, "email", None)
    if not email: return
    ctx = {
        "chamado": chamado,
        "solicitante": chamado.solicitante,
        "url": f"/solicitacoes/chamados/{chamado.pk}/",
    }
    send_email(
        kind="ticket_created",
        to_email=email,
        context=ctx,
        ref={"app": "solicitacoes", "model": "Chamado", "pk": chamado.pk},
    )

def notify_ticket_reply(mensagem, destinatario: Optional[str] = None):
    chamado = mensagem.chamado
    # se o autor é admin/atendente, manda para solicitante; se é solicitante, manda para atendente (se disponível)
    if destinatario:
        email = destinatario
    else:
        if getattr(mensagem.autor, "is_staff", False) or getattr(mensagem.autor, "is_superuser", False):
            email = getattr(chamado.solicitante, "email", None)
        else:
            email = getattr(chamado, "atendente_email", None) or None
    if not email: return
    ctx = {
        "chamado": chamado,
        "mensagem": mensagem,
        "autor": mensagem.autor,
        "url": f"/solicitacoes/chamados/{chamado.pk}/",
    }
    send_email(
        kind="ticket_reply",
        to_email=email,
        context=ctx,
        ref={"app": "solicitacoes", "model": "Chamado", "pk": chamado.pk},
    )

def notify_ticket_status(chamado, old_status, new_status, destinatario: Optional[str] = None):
    email = destinatario or getattr(chamado.solicitante, "email", None)
    if not email: return
    ctx = {
        "chamado": chamado,
        "old_status": old_status,
        "new_status": new_status,
        "url": f"/solicitacoes/chamados/{chamado.pk}/",
    }
    send_email(
        kind="ticket_status",
        to_email=email,
        context=ctx,
        ref={"app": "solicitacoes", "model": "Chamado", "pk": chamado.pk},
    )
