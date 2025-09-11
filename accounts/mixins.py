# accounts/mixins.py
from django.contrib.auth.mixins import UserPassesTestMixin

class OnlyManagersMixin(UserPassesTestMixin):
    """
    Permite acesso para:
      - superusuário
      - perfis ADMINISTRADOR, GESTOR e SUPER_TI
      - ou membros de grupos com esses mesmos nomes
    """
    raise_exception = True  # 403 em vez de redirecionar
    allowed_profiles = {"ADMINISTRADOR", "GESTOR", "SUPER_TI"}

    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False

        if u.is_superuser:
            return True

        # por perfil (campo do seu User)
        if getattr(u, "perfil", None) in self.allowed_profiles:
            return True

        # por grupo (você sincroniza grupos = perfil)
        if u.groups.filter(name__in=self.allowed_profiles).exists():
            return True

        return False
