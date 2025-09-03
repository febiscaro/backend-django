
# accounts/mixins.py
from django.contrib.auth.mixins import UserPassesTestMixin

class OnlyManagersMixin(UserPassesTestMixin):
    """
    Permite: superuser, ADMIN e GESTOR (via campo perfil ou via grupos).
    """
    raise_exception = True  # retorna 403 em vez de redirecionar

    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False
        in_groups = u.groups.filter(name__in=["ADMIN", "GESTOR"]).exists()
        by_profile = getattr(u, "perfil", None) in ("ADMIN", "GESTOR")
        return u.is_superuser or in_groups or by_profile
