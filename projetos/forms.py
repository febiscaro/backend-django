from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from .models import CostCenter

_domain_validator = RegexValidator(
    regex=r"^[a-z0-9.-]+\.[a-z]{2,}$",
    message="Informe um domínio válido, ex.: empresa.com.br"
)

class CostCenterCreateForm(forms.ModelForm):
    # Domínios permitidos: um por linha (aceita vírgula também)
    dominios = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "ex.: empresa.com.br\nfilial.empresa.com.br"}),
        help_text="Um domínio por linha."
    )

    class Meta:
        model = CostCenter
        fields = [
            "nome", "codigo", "cliente",
            "contato_email", "contato_nome", "contato_telefone",
            "contrato_inicio", "contrato_fim",
            "orcamento_total", "horas_previstas",
            "background_image", "ativo",
        ]

    def clean_dominios(self):
        txt = (self.cleaned_data.get("dominios") or "").strip()
        if not txt:
            return []
        items = []
        # permite separar por quebras de linha e/ou vírgulas
        for raw in txt.replace(",", "\n").splitlines():
            dom = raw.strip().lower()
            if not dom:
                continue
            _domain_validator(dom)
            items.append(dom)
        # dedup e ordena
        return sorted(set(items))

    def clean_contato_email(self):
        email = (self.cleaned_data.get("contato_email") or "").strip()
        if not email:
            return email  # campo opcional
        if "@" not in email:
            raise ValidationError("Informe um e-mail válido (faltou @).")
        return email

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("contato_email")
        domains = cleaned.get("dominios") or []
        if email:
            domain = email.rsplit("@", 1)[-1].lower()
            # Se domínios foram informados, o e-mail do contato deve pertencer a um deles
            if domains and domain not in set(domains):
                raise ValidationError({"contato_email": f"O domínio do e-mail do contato deve estar entre os permitidos: {', '.join(domains)}."})
        return cleaned
