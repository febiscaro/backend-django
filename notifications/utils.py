# notifications/utils.py
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

# Grupos que devem receber notificações "de admin".
# Incluí variações comuns para evitar erro por nome diferente.
GRUPOS_ADMINISH = {
    "Administrativo", "Atendimento", "Gestor", "Suporte",
    "ADMIN", "Admin", "ADM",
}

def users_adminish():
    """
    Retorna usuários que devem ser notificados como 'admin-ish':
    - superusuários (is_superuser=True), ou
    - usuários que participam de AO MENOS UM dos grupos acima.
    
    OBS: NÃO usa is_staff. Assim, ninguém ganha acesso ao /admin por causa disso.
    """
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name__in=GRUPOS_ADMINISH))
        .distinct()
    )

def emails(users_qs):
    return [u.email for u in users_qs if getattr(u, "email", None)]

def get_atendente_user(chamado):
    """
    Se seu modelo tiver FK 'atendente' para User, isso pega o usuário.
    Se for só 'atendente_nome' (texto), retorna None.
    """
    att = getattr(chamado, "atendente", None)
    return att if att and getattr(att, "is_active", False) else None
