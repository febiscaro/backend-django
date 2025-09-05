# notifications/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.html import escape

from notifications.services import send_simple_email
from notifications.utils import users_adminish, emails, get_atendente_user
from notifications.models import Notification

from solicitacoes.models import Chamado, ChamadoMensagem


# --------- helpers ---------
def _as_body_html(text: str) -> str:
    # preserva quebras de linha simples
    return f"<p>{escape(text).replace(chr(10), '<br>')}</p>"

def _notify_web(to_emails, subject: str, body: str, ref_app: str, ref_model: str, ref_pk):
    """
    Cria itens de Notification (canal 'web') para alimentar o sininho.
    Funciona mesmo sem campos to_user/read_at.
    """
    for mail in (to_emails or []):
        if not mail:
            continue
        Notification.objects.create(
            kind="generic",
            subject=subject,
            body_text=body,
            body_html=_as_body_html(body),
            to_email=mail,
            channel="web",
            ref_app=ref_app,
            ref_model=ref_model,
            ref_pk=str(ref_pk),
            is_sent=True,  # apenas p/ diferenciar de envio de e-mail
        )


# 1) NOVO CHAMADO
#    - E-mail para admin-ish
#    - Sininho para solicitante E para admin-ish (foi o que faltou p/ o Administrativo ver)
@receiver(post_save, sender=Chamado)
def on_chamado_created(sender, instance: Chamado, created: bool, **kwargs):
    if not created:
        return

    subject = f"[Enprodes] Nova solicitação #{instance.id}"
    body = (
        f"Uma nova solicitação foi aberta.\n"
        f"ID: {instance.id}\n"
        f"Tipo: {getattr(instance.tipo, 'nome', '')}\n"
        f"Solicitante: {getattr(instance.solicitante, 'get_username', lambda: '')() or instance.solicitante}\n"
        f"Status: {getattr(instance, 'status', '')}\n"
        f"Link: /solicitacoes/chamados/{instance.id}/\n"
    )

    admin_emails = emails(users_adminish())

    # e-mail para administradores
    send_simple_email(subject, body, admin_emails)

    # sininho do solicitante
    solicitante_email = getattr(instance.solicitante, "email", None)
    if solicitante_email:
        _notify_web(
            [solicitante_email], subject, body,
            ref_app="solicitacoes", ref_model="Chamado", ref_pk=instance.id
        )

    # sininho dos administradores (isto habilita o badge/itens p/ o perfil Administrativo)
    if admin_emails:
        _notify_web(
            admin_emails, subject, body,
            ref_app="solicitacoes", ref_model="Chamado", ref_pk=instance.id
        )


# 2) NOVA MENSAGEM
#    Notifica SEMPRE a "outra parte":
#    - Se há atendente:
#        * autor = atendente  -> notifica solicitante
#        * autor = solicitante -> notifica atendente
#    - Se NÃO há atendente:
#        * autor = solicitante -> notifica admin-ish
#        * autor = admin-ish/qualquer -> notifica solicitante
@receiver(post_save, sender=ChamadoMensagem)
def on_chamado_nova_mensagem(sender, instance: ChamadoMensagem, created: bool, **kwargs):
    if not created:
        return

    ch = instance.chamado

    # respeita lógica de mensagens públicas
    vis_publica = getattr(ChamadoMensagem, "PUBLICA", "publica")
    if getattr(instance, "visibilidade", vis_publica) != vis_publica:
        return

    subject = f"[Enprodes] Nova mensagem no chamado #{ch.id}"
    body = (
        f"Houve uma nova mensagem no chamado #{ch.id}.\n"
        f"Autor: {getattr(instance.autor, 'get_username', lambda: '')() or instance.autor}\n"
        f"Link: /solicitacoes/chamados/{ch.id}/\n"
    )

    solicitante_email = getattr(ch.solicitante, "email", None)
    atendente = get_atendente_user(ch)
    atendente_email = getattr(atendente, "email", None) if atendente else None
    autor_id = getattr(instance.autor, "id", None)

    if atendente:
        # há atendente designado
        if autor_id == getattr(atendente, "id", None):
            # quem escreveu foi o atendente -> notifica solicitante
            if solicitante_email:
                send_simple_email(subject, body, [solicitante_email])
                _notify_web([solicitante_email], subject, body,
                            ref_app="solicitacoes", ref_model="Chamado", ref_pk=ch.id)
        else:
            # quem escreveu foi o solicitante (ou outro) -> notifica atendente
            if atendente_email:
                send_simple_email(subject, body, [atendente_email])
                _notify_web([atendente_email], subject, body,
                            ref_app="solicitacoes", ref_model="Chamado", ref_pk=ch.id)
        return

    # sem atendente ainda
    admin_emails = emails(users_adminish())

    # se autor é solicitante -> notifica admin-ish
    if autor_id == getattr(ch.solicitante, "id", None):
        if admin_emails:
            send_simple_email(subject, body, admin_emails)
            _notify_web(admin_emails, subject, body,
                        ref_app="solicitacoes", ref_model="Chamado", ref_pk=ch.id)
    else:
        # autor não é solicitante -> notifica solicitante (se houver e-mail)
        if solicitante_email:
            send_simple_email(subject, body, [solicitante_email])
            _notify_web([solicitante_email], subject, body,
                        ref_app="solicitacoes", ref_model="Chamado", ref_pk=ch.id)


# 3) MUDANÇA DE STATUS → e-mail + sininho para solicitante
@receiver(pre_save, sender=Chamado)
def _capture_old_status(sender, instance: Chamado, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.only("status").get(pk=instance.pk)
        instance.__old_status = old.status
    except sender.DoesNotExist:
        pass


@receiver(post_save, sender=Chamado)
def on_chamado_status_changed(sender, instance: Chamado, created: bool, **kwargs):
    if created:
        return

    old_status = getattr(instance, "__old_status", None)
    new_status = instance.status
    if old_status is None or old_status == new_status:
        return

    subject = f"[Enprodes] Seu chamado #{instance.id} mudou de status"
    body = (
        f"O status do seu chamado #{instance.id} foi alterado.\n"
        f"De: {old_status}\n"
        f"Para: {new_status}\n"
        f"Link: /solicitacoes/chamados/{instance.id}/\n"
    )

    destinatario = getattr(instance.solicitante, "email", None)
    if destinatario:
        send_simple_email(subject, body, [destinatario])
        _notify_web([destinatario], subject, body,
                    ref_app="solicitacoes", ref_model="Chamado", ref_pk=instance.id)
