# -*- coding: utf-8 -*-
"""
models.py — User model customizado com login por CPF, validação de e-mail corporativo,
gerenciador (UserManager) para criação de usuários/superusuários, sincronização automática
de grupos conforme o perfil e utilitário de senha temporária.
"""

from django.db import models, transaction
from django.contrib.auth.models import (
    AbstractBaseUser,   # hash/gestão de senha e campos básicos de autenticação
    PermissionsMixin,   # grupos, permissões e is_superuser
)
from django.contrib.auth.base_user import BaseUserManager
from django.utils import timezone
import secrets

# >>> Validadores centralizados no módulo validators.py <<<
from .validators import validate_cpf, validate_company_email


# ---------------------- Manager customizado ----------------------
class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        """
        Permite que Admin/autenticação usem o CPF "natural".
        Normaliza antes de buscar.
        """
        return self.get(cpf=validate_cpf(username))

    @transaction.atomic
    def _create_user(self, cpf, password=None, **extra_fields):
        """
        Criação interna:
        - Normaliza/valida CPF e e-mail.
        - Define senha (ou inutilizável).
        - Garante date_joined/is_active/perfil se ausentes.
        - Roda clean() antes do save.
        """
        if not cpf:
            raise ValueError("CPF é obrigatório.")

        cpf = validate_cpf(cpf)

        email = extra_fields.pop("email", None)
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email)
        email = validate_company_email(email)

        extra_fields.setdefault("date_joined", timezone.now())
        extra_fields.setdefault("is_active", True)
        # padronizado com os choices do modelo:
        extra_fields.setdefault("perfil", "COLABORADOR")

        user = self.model(cpf=cpf, email=email, **extra_fields)
        user.clean()  # reaproveita validações do modelo

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_user(self, cpf, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(cpf, password, **extra_fields)

    def create_superuser(self, cpf, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser precisa is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser precisa is_superuser=True.")

        return self._create_user(cpf, password, **extra_fields)


# ---------------------- Modelo de Usuário ----------------------
class User(AbstractBaseUser, PermissionsMixin):
    """
    Usuário com autenticação por CPF.
    - AbstractBaseUser: senha/last_login
    - PermissionsMixin: grupos/permissões/is_superuser
    """

    # ---- Choices fixos ----
    # (códigos padronizados para facilitar regra de autorização/menus)
    PERFIL_ADMIN       = "ADMINISTRADOR"
    PERFIL_GESTOR      = "GESTOR"
    PERFIL_COLAB       = "COLABORADOR"
    PERFIL_SUPER_TI    = "SUPER_TI"

    PERFIS = (
        (PERFIL_ADMIN,    "Administrador"),
        (PERFIL_GESTOR,   "Gestor"),
        (PERFIL_COLAB,    "Colaborador"),
        (PERFIL_SUPER_TI, "Super TI"),
    )

    SETORES = (
        ("FROTA",               "FROTA"),
        ("ADM/RH/DP",           "ADM/RH/DP"),
        ("SMS",                 "SMS"),
        ("PLANEJAMENTO",        "PLANEJAMENTO"),
        ("RTCT",                "RTCT"),
        ("ELÉTRICA/AUTOMAÇÃO",  "ELÉTRICA/AUTOMAÇÃO"),
        ("PPCI/MECÂNICA",       "PPCI/MECÂNICA"),
        ("CIVIL/ARQUITETURA",   "CIVIL/ARQUITETURA"),
        ("PRODUÇÃO",            "PRODUÇÃO"),
        ("NOVOS NEGÓCIOS",      "NOVOS NEGÓCIOS"),
        ("DOC DE SEGURANÇA",    "DOC DE SEGURANÇA"),
        ("PROJETO CIVITAS",     "PROJETO CIVITAS"),
    )

    # código "NA" incluído nas choices para não quebrar forms/admin
    GESTAO_SEM = "NA"
    GESTOES = (
        (GESTAO_SEM,  "Sem gestão"),
        ("RICARDO",   "RICARDO MIRANDA"),
        ("FERNANDA",  "FERNANDA LAZZARI"),
        ("IVAN",      "IVAN MORAIS"),
        ("ANDRE",     "ANDRÉ HILLENSHEIM"),
        ("LUIZ",      "LUIZ EDUARDO OLIVEIRA"),
    )

    # ---- Campos principais ----
    cpf = models.CharField(
        "CPF",
        max_length=14,        # aceita pontuado na entrada; normaliza no clean()
        unique=True,
        help_text="Somente números (11 dígitos)",
    )
    nome_completo = models.CharField("Nome completo", max_length=150)
    email = models.EmailField("E-mail corporativo", unique=True)
    data_nascimento = models.DateField("Data de nascimento", null=True, blank=True)

    # defaults agora existentes nas choices
    setor  = models.CharField("Setor",  max_length=30, choices=SETORES, default="ADM/RH/DP")
    cargo  = models.CharField("Cargo",  max_length=30, choices=(
        ("ENGENHEIRO",     "ENGENHEIRO"),
        ("COORDENADOR",    "COORDENADOR"),
        ("TÉCNICO",        "TÉCNICO"),
        ("ESTAGIARIO",     "ESTAGIARIO"),
        ("ANALISTA",       "ANALISTA"),
        ("DIRETOR",        "DIRETOR"),
        ("ASSISTENTE ADM", "ASSISTENTE ADM"),
        ("PROJETISTA",     "PROJETISTA"),
    ), default="ANALISTA")
    perfil = models.CharField("Perfil de acesso", max_length=20, choices=PERFIS, default=PERFIL_COLAB)
    # aumentei o max_length e corrigi choices; mantém "NA" como default válido
    gestao = models.CharField("Área de Gestão", max_length=30, choices=GESTOES, default=GESTAO_SEM)

    # ---- Flags padrão ----
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # ---- Manager customizado ----
    objects = UserManager()

    USERNAME_FIELD  = "cpf"
    REQUIRED_FIELDS = ["nome_completo", "email"]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    # ---- Validações/Hooks ----
    def clean(self):
        self.cpf = validate_cpf(self.cpf)
        self.email = validate_company_email(self.email)

    def get_short_name(self):
        return (self.nome_completo or "").strip().split(" ")[0]

    def __str__(self):
        return f"{self.nome_completo} ({self.cpf})"

    # ---- Grupos por perfil/gestão ----
    def sync_groups_from_perfil(self):
        from django.contrib.auth.models import Group

        grupos = []
        g_perfil, _ = Group.objects.get_or_create(name=self.perfil)
        grupos.append(g_perfil)

        # Se a pessoa pertence a alguma gestão específica (≠ "NA"), adiciona também
        if self.gestao and self.gestao != self.GESTAO_SEM:
            g_gestao, _ = Group.objects.get_or_create(name=f"GESTAO_{self.gestao}")
            grupos.append(g_gestao)

        self.groups.set(grupos)

    def save(self, *args, **kwargs):
        """
        Salva e sincroniza grupos após mudança de perfil ou gestão.
        Nota: updates em massa (QuerySet.update) não chamam save().
        """
        perfil_antigo = gestao_antiga = None
        if self.pk:
            qs = type(self).objects.filter(pk=self.pk)
            perfil_antigo = qs.values_list("perfil",  flat=True).first()
            gestao_antiga = qs.values_list("gestao", flat=True).first()

        super().save(*args, **kwargs)

        if perfil_antigo != self.perfil or gestao_antiga != self.gestao:
            self.sync_groups_from_perfil()

    # ---- Senha temporária ----
    def set_temporary_password(self, length: int = 10) -> str:
        temp = secrets.token_urlsafe(length)[:length]
        self.set_password(temp)
        self.save(update_fields=["password"])
        return temp
