from django.contrib.auth.forms import AuthenticationForm
from django import forms

from .validators import validate_cpf  # <- normaliza/valida o CPF

class CPFAuthenticationForm(AuthenticationForm):
    """
    Formulário de login usando CPF.
    - Ajusta label/placeholders
    - Normaliza o CPF no clean_username (aceita com ou sem pontuação)
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "CPF"
        self.fields["username"].widget.attrs.update({
            "placeholder": "Somente números",
            "inputmode": "numeric",
            "autocomplete": "username",
        })
        self.fields["password"].widget.attrs.update({
            "placeholder": "Sua senha",
            "autocomplete": "current-password",
        })

    def clean_username(self):
        # Normaliza/valida o CPF digitado (com ou sem pontuação)
        username = self.cleaned_data.get("username", "")
        return validate_cpf(username)
