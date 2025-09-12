from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    ReadOnlyPasswordHashField,
    PasswordChangeForm,
)
from .models import User
from .validators import validate_cpf, validate_company_email


# ---------- Form do LOGIN (usado pelo LoginView) ----------
class CPFAuthenticationForm(AuthenticationForm):
    """Formulário de autenticação que renomeia username -> CPF e aplica classes Bootstrap."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "CPF"
        self.fields["username"].widget.attrs.update({
            "placeholder": "Somente números",
            "class": "form-control",
            "inputmode": "numeric",
            "autocomplete": "username",
        })
        self.fields["password"].widget.attrs.update({
            "placeholder": "Sua senha",
            "class": "form-control",
            "autocomplete": "current-password",
        })


# ---------- Criação de usuário (admin/uso interno) ----------
class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Confirmação de senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"})
    )

    class Meta:
        model = User
        fields = ("cpf", "nome_completo", "email", "data_nascimento", "setor", "cargo", "perfil", "gestao")
        widgets = {
            "cpf":             forms.TextInput(attrs={"class": "form-control", "placeholder": "Somente números", "inputmode": "numeric"}),
            "nome_completo":   forms.TextInput(attrs={"class": "form-control", "placeholder": "Nome completo"}),
            "email":           forms.EmailInput(attrs={"class": "form-control", "placeholder": "seu.nome@mirabit.com.br"}),
            "data_nascimento": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            # dropdowns (choices vêm do modelo)
            "setor":           forms.Select(attrs={"class": "form-select"}),
            "cargo":           forms.Select(attrs={"class": "form-select"}),
            "perfil":          forms.Select(attrs={"class": "form-select"}),
            "gestao":          forms.Select(attrs={"class": "form-select"}),
        }

    def clean_cpf(self):
        return validate_cpf(self.cleaned_data.get("cpf"))

    def clean_email(self):
        return validate_company_email(self.cleaned_data.get("email"))

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("As senhas não coincidem.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


# ---------- Edição de usuário (admin/uso interno) ----------
class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Senha",
        help_text="Você pode alterar a senha usando o botão 'Alterar senha' acima."
    )

    class Meta:
        model = User
        fields = (
            "cpf", "nome_completo", "email", "data_nascimento",
            "setor", "cargo", "perfil", "gestao",
            "password", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"
        )
        widgets = {
            "cpf":             forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "nome_completo":   forms.TextInput(attrs={"class": "form-control"}),
            "email":           forms.EmailInput(attrs={"class": "form-control"}),
            "data_nascimento": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            # dropdowns:
            "setor":           forms.Select(attrs={"class": "form-select"}),
            "cargo":           forms.Select(attrs={"class": "form-select"}),
            "perfil":          forms.Select(attrs={"class": "form-select"}),
            "gestao":          forms.Select(attrs={"class": "form-select"}),
            "is_active":       forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_staff":        forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_superuser":    forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "groups":          forms.SelectMultiple(attrs={"class": "form-select"}),
            "user_permissions":forms.SelectMultiple(attrs={"class": "form-select"}),
        }


# ---------- (Opcional) Form de edição no FRONT (página de gestão) ----------
class FrontUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("nome_completo", "cpf", "email", "data_nascimento", "setor", "cargo", "perfil", "gestao", "is_active")
        widgets = {
            "nome_completo":   forms.TextInput(attrs={"class": "form-control"}),
            "cpf":             forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "email":           forms.EmailInput(attrs={"class": "form-control"}),
            "data_nascimento": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            # dropdowns:
            "setor":           forms.Select(attrs={"class": "form-select"}),
            "cargo":           forms.Select(attrs={"class": "form-select"}),
            "perfil":          forms.Select(attrs={"class": "form-select"}),
            "gestao":          forms.Select(attrs={"class": "form-select"}),
            "is_active":       forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_cpf(self):
        return validate_cpf(self.cleaned_data.get("cpf"))

    def clean_email(self):
        return validate_company_email(self.cleaned_data.get("email"))


class PrettyPasswordChangeForm(PasswordChangeForm):
    """Aplica classes do Bootstrap e placeholders nos campos da troca de senha."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Sua senha atual",
            "autocomplete": "current-password",
        })
        self.fields["new_password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Nova senha",
            "autocomplete": "new-password",
        })
        self.fields["new_password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirme a nova senha",
            "autocomplete": "new-password",
        })


# ---------- Form de "Meu perfil" (edição pelo próprio usuário) ----------
class PerfilForm(forms.ModelForm):
    """Usado na página 'Meu perfil' para o próprio usuário atualizar dados básicos (sem trocar CPF/perfil/gestão)."""
    class Meta:
        model = User
        fields = ("nome_completo", "email", "data_nascimento", "setor", "cargo")
        labels = {
            "nome_completo": "Nome completo",
            "email": "E-mail",
            "data_nascimento": "Data de nascimento",
            "setor": "Setor",
            "cargo": "Cargo",
        }
        widgets = {
            "nome_completo":   forms.TextInput(attrs={"class": "form-control", "placeholder": "Seu nome completo"}),
            "email":           forms.EmailInput(attrs={"class": "form-control", "placeholder": "seu.nome@mirabit.com.br", "autocomplete": "email"}),
            "data_nascimento": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            # dropdowns:
            "setor":           forms.Select(attrs={"class": "form-select"}),
            "cargo":           forms.Select(attrs={"class": "form-select"}),
        }

    def clean_email(self):
        return validate_company_email(self.cleaned_data.get("email"))
