from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.apps import apps

class Command(BaseCommand):
    help = "Cria grupos ADMIN, GESTOR e COLAB com permissões base"

    def handle(self, *args, **opts):
        User = apps.get_model("accounts", "User")

        # cria grupos
        admin_g, _ = Group.objects.get_or_create(name="ADMIN")
        gestor_g, _ = Group.objects.get_or_create(name="GESTOR")
        colab_g, _  = Group.objects.get_or_create(name="COLAB")

        # permissões do modelo User
        perms = Permission.objects.filter(content_type__app_label="accounts",
                                          content_type__model="user")

        # ADMIN: tudo
        admin_g.permissions.set(perms)

        # GESTOR: ver e alterar (sem deletar)
        gestor_g.permissions.set(perms.filter(codename__in=[
            "view_user","change_user","add_user"
        ]))

        # COLAB: só ver a si mesmo (vamos controlar na view depois). No admin fica sem permissão de edição
        colab_g.permissions.set(perms.filter(codename__in=["view_user"]))

        self.stdout.write(self.style.SUCCESS("Grupos criados/atualizados."))
