from django.contrib.auth.forms import AuthenticationForm
from django import forms

class CPFAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "CPF"
        self.fields["username"].widget.attrs.update({"placeholder": "Somente números"})
        self.fields["password"].widget.attrs.update({"placeholder": "Sua senha"})

