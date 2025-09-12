# notifications/utils.py
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

def users_adminish():
    """
    Usuários que devem ver/receber notificações gerais de chamados.
    Inclui: superuser, staff, grupos Gestor/Administrativo/Suporte, e perfis ADMIN/ADMINISTRATIVO.
    """
    return (
        User.objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True) |
            Q(is_staff=True) |
            Q(groups__name__in=["Gestor", "Administrativo", "Suporte"]) |
            Q(perfil__in=["ADMIN", "ADMINISTRATIVO", "ADMINISTRADOR"])
        )
        .distinct()
    )

def emails(users_qs):
    """
    Extrai e-mails válidos do queryset/lista de usuários, sem duplicatas.
    """
    unique = []
    seen = set()
    for u in users_qs:
        e = (getattr(u, "email", "") or "").strip().lower()
        if e and e not in seen:
            seen.add(e)
            unique.append(e)
    return unique

def get_atendente_user(chamado):
    """
    Se você tiver um FK (ex.: chamado.atendente), use-o aqui.
    Caso só exista 'atendente_nome' (texto), tenta casar pelo nome.
    Ajuste conforme seu modelo real.
    """
    nome = (getattr(chamado, "atendente_nome", "") or "").strip()
    if not nome:
        return None
    try:
        return User.objects.get(nome_completo__iexact=nome, is_active=True)
    except User.DoesNotExist:
        # fallback bem flexível
        return (
            User.objects.filter(
                is_active=True
            ).filter(
                Q(nome_completo__iexact=nome) |
                Q(first_name__iexact=nome) |
                Q(last_name__iexact=nome) |
                Q(username__iexact=nome)
            ).first()
        )
