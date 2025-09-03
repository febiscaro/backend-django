# -*- coding: utf-8 -*-
"""
models.py — User model customizado com login por CPF, validação de e-mail corporativo,
gerenciador (UserManager) para criação de usuários/superusuários, sincronização automática
de grupos conforme o perfil e utilitário de senha temporária.
"""

# --- Imports principais do Django/modelo e utilidades padrão ---
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,   # fornece hash/gestão de senha e campos básicos de autenticação
    PermissionsMixin,   # adiciona grupos, permissões e campo is_superuser
    BaseUserManager,    # base para criar o manager customizado do usuário
)
from django.core.exceptions import ValidationError  # para levantar erros de validação de campo
from django.utils import timezone  # para datas cientes de timezone (USE_TZ)
import re        # regex, usado para extrair apenas dígitos do CPF
import secrets   # gerador de tokens seguros (senha temporária)

# Conjunto de domínios de e-mail corporativos aceitos.
# Sugestão: mover para settings.ALLOWED_EMAIL_DOMAINS se quiser configurar por ambiente.
ALLOWED_EMAIL_DOMAINS = {"mirabit.com.br", "enprodes.com.br"}


# --- Funções de validação utilitárias ----------------------------------------------------------

def validate_cpf(value: str):
    """
    Valida e normaliza um CPF de forma simples:
      - Remove qualquer caractere que não seja dígito.
      - Exige que o resultado tenha exatamente 11 dígitos.
    Observação: não implementa verificação de dígitos verificadores.
    """
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 11:
        raise ValidationError("CPF deve conter 11 dígitos numéricos.")
    return digits


def validate_company_email(value: str):
    """
    Valida e normaliza o e-mail corporativo:
      - Remove espaços e converte para lowercase.
      - Exige presença de '@'.
      - Restringe o domínio ao conjunto ALLOWED_EMAIL_DOMAINS.
    """
    value = (value or "").strip().lower()
    if "@" not in value:
        raise ValidationError("E-mail inválido.")
    domain = value.split("@", 1)[1]
    if domain not in ALLOWED_EMAIL_DOMAINS:
        # Dica: usar ', '.join(sorted(...)) se quiser ordem estável na mensagem
        raise ValidationError(f"E-mail deve ser dos domínios: {', '.join(ALLOWED_EMAIL_DOMAINS)}.")
    return value


# --- Manager customizado para o User -----------------------------------------------------------

# accounts/models.py
from django.contrib.auth.base_user import BaseUserManager
# ... seus outros imports

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, cpf, password, **extra_fields):
        # Tira 'email' de extra_fields para não passar duplicado
        email = extra_fields.pop('email', None)
        if email:
            email = self.normalize_email(email)
        else:
            # Se quiser permitir criar usuário sem email, remova este raise
            raise ValueError("O e-mail é obrigatório.")

        user = self.model(cpf=cpf, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, cpf, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(cpf, password, **extra_fields)

    def create_superuser(self, cpf, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser precisa is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser precisa is_superuser=True.')

        return self._create_user(cpf, password, **extra_fields)



# --- Modelo de Usuário customizado -------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de usuário customizado com autenticação por CPF.
    - AbstractBaseUser: fornece infraestrutura de senha/last_login.
    - PermissionsMixin: acrescenta grupos, permissões e is_superuser.
    """

    # Choices para o campo 'perfil' (valor armazenado, rótulo legível)
    PERFIS = (
        ("ADMIN", "Administrador"),
        ("GESTOR", "Gestor"),
        ("COLAB", "Colaborador"),
    )

    # --- Campos de identificação e perfil ---
    cpf = models.CharField(
        "CPF",
        max_length=14,        # valor "folgado" para aceitar formato com pontuação; será normalizado no clean()
        unique=True,
        help_text="Somente números (11 dígitos)"
    )
    nome_completo = models.CharField("Nome completo", max_length=150)
    email = models.EmailField("E-mail corporativo", unique=True)
    data_nascimento = models.DateField("Data de nascimento", null=True, blank=True)

    setor = models.CharField("Setor", max_length=80, blank=True, default="")
    cargo = models.CharField("Cargo", max_length=80, blank=True, default="")
    perfil = models.CharField("Perfil de acesso", max_length=10, choices=PERFIS, default="COLAB")

    # --- Flags padrão de usuário ---
    is_active = models.BooleanField(default=True)   # desativa login sem apagar usuário
    is_staff = models.BooleanField(default=False)   # acesso ao Django Admin
    date_joined = models.DateTimeField(default=timezone.now)  # quando a conta foi criada

    # Manager customizado
    objects = UserManager()

    # Define o campo usado como "nome de usuário" (login)
    USERNAME_FIELD = "cpf"

    # Campos adicionais solicitados pelo createsuperuser (além de USERNAME_FIELD e password)
    REQUIRED_FIELDS = ["nome_completo", "email"]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    # --- Hooks/Utilidades do modelo ---

    def clean(self):
        """
        Hook de validação/normalização de instância (usado por ModelForms/admin).
        - Normaliza CPF para 11 dígitos.
        - Normaliza/valida e-mail corporativo e domínio permitido.
        """
        self.cpf = validate_cpf(self.cpf)
        self.email = validate_company_email(self.email)

    def get_short_name(self):
        """
        Retorna um 'primeiro nome' para exibição em cabeçalhos/menus.
        """
        return self.nome_completo.split(" ")[0]

    def __str__(self):
        """
        Representação legível (útil no admin e em logs).
        """
        return f"{self.nome_completo} ({self.cpf})"

    # --- Sincronização de grupos conforme o perfil selecionado ---

    def sync_groups_from_perfil(self):
        """
        Mantém o usuário exclusivamente no grupo cujo nome é igual ao valor do campo 'perfil'.
        - Cria o Group se ainda não existir (get_or_create).
        - Substitui todos os grupos do usuário por esse grupo (self.groups.set([g])).
        Observação: se você quiser permitir múltiplos grupos, troque por self.groups.add(g).
        """
        from django.contrib.auth.models import Group
        g, _ = Group.objects.get_or_create(name=self.perfil)
        self.groups.set([g])  # mantém apenas o grupo do perfil

    def save(self, *args, **kwargs):
        """
        Salva a instância e, em seguida, sincroniza os grupos com base no 'perfil'.
        Observação:
        - Em updates em massa (QuerySet.update), este método não é chamado. Caso mude o
          'perfil' em bulk, rode uma tarefa/management command para ressincronizar.
        """
        super().save(*args, **kwargs)
        self.sync_groups_from_perfil()

    def set_temporary_password(self, length: int = 10) -> str:
        """
        Gera e define uma senha temporária segura (com hash) e retorna a senha em claro.
        - Usa secrets.token_urlsafe(length) e recorta para o tamanho desejado.
        - Salva apenas o hash (update_fields=["password"]).
        Uso típico: exibir para o admin enviar ao usuário por canal seguro.
        """
        temp = secrets.token_urlsafe(length)[:length]
        self.set_password(temp)                 # armazena hash
        self.save(update_fields=["password"])   # persiste somente o campo de senha
        return temp
