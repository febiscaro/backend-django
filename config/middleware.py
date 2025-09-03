from django.http import HttpResponseForbidden

class AccessControlMiddleware:
    """
    Controle de acesso para páginas específicas.
    - /admin/  → apenas superusuários
    - /accounts/usuarios/ → apenas superuser, admin ou gestor
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Bloqueia admin para não-superusers
        if path.startswith("/admin/"):
            if request.user.is_authenticated and not request.user.is_superuser:
                return HttpResponseForbidden("Admin: acesso permitido apenas a superusuários.")

        # Bloqueia página de usuários para não autorizados
        if path.startswith("/accounts/usuarios/"):
            if request.user.is_authenticated:
                perfil = getattr(request.user, "perfil", "").lower()
                if not (request.user.is_superuser or perfil in ["admin", "gestor"]):
                    return HttpResponseForbidden("Usuários: acesso não autorizado.")
            else:
                return HttpResponseForbidden("Usuários: acesso não autorizado.")

        return self.get_response(request)
