# -*- coding: utf-8 -*-
import re
from django.conf import settings
from django.core.exceptions import ValidationError

# Domínios permitidos:
# - Se existir settings.ALLOWED_EMAIL_DOMAINS, usa ele.
# - Senão, usa este fallback local.
DEFAULT_ALLOWED_EMAIL_DOMAINS = {"mirabit.com.br", "enprodes.com.br"}

def _get_allowed_domains():
    domains = getattr(settings, "ALLOWED_EMAIL_DOMAINS", None)
    if domains:
        # aceita list/tuple/set no settings
        return set(domains)
    return DEFAULT_ALLOWED_EMAIL_DOMAINS

def validate_cpf(value: str) -> str:
    """
    Normaliza e valida CPF (formato simples):
      - Mantém apenas dígitos
      - Exige 11 dígitos
    """
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 11:
        raise ValidationError("CPF deve conter 11 dígitos numéricos.")
    return digits

def validate_company_email(value: str) -> str:
    """
    Valida e normaliza e-mail corporativo:
      - strip + lowercase
      - precisa ter '@'
      - domínio deve estar na lista permitida
    """
    value = (value or "").strip().lower()
    if "@" not in value:
        raise ValidationError("E-mail inválido.")
    domain = value.split("@", 1)[1]
    allowed = _get_allowed_domains()
    if domain not in allowed:
        raise ValidationError(f"E-mail deve ser dos domínios: {', '.join(sorted(allowed))}.")
    return value
