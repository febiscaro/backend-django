from django import forms
from .models import TipoSolicitacao, PerguntaTipoSolicitacao
from .models import ChamadoMensagem


class TipoSolicitacaoForm(forms.ModelForm):
    class Meta:
        model = TipoSolicitacao
        fields = ['nome', 'descricao', 'ativo', 'setores_permitidos']  # + setores_permitidos
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'setores_permitidos': forms.TextInput(attrs={
                'placeholder': "Ex.: RH; Financeiro; TI  (vazio = todos)"
            }),
        }


class PerguntaTipoSolicitacaoForm(forms.ModelForm):
    class Meta:
        model = PerguntaTipoSolicitacao
        fields = ['ordem', 'texto', 'tipo_campo', 'obrigatoria', 'opcoes', 'ajuda', 'ativa']
        widgets = {
            'ajuda': forms.TextInput(attrs={'placeholder': 'Texto de ajuda (opcional)'}),
            'opcoes': forms.TextInput(attrs={'placeholder': 'Para escolha(s), separe por ;'}),
        }


class NovaSolicitacaoTipoForm(forms.Form):
    tipo = forms.ModelChoiceField(
        queryset=TipoSolicitacao.objects.none(),
        label='Tipo de solicitação'
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = TipoSolicitacao.objects.filter(ativo=True)
        if user is not None:
            # usa o helper visivel_para(user)
            allowed_ids = [t.id for t in qs if t.visivel_para(user)]
            qs = qs.filter(pk__in=allowed_ids)
        self.fields['tipo'].queryset = qs.order_by('nome')






class ChamadoMensagemForm(forms.ModelForm):
    class Meta:
        model = ChamadoMensagem
        fields = ["texto", "anexo", "visibilidade"]
        widgets = {
            "texto": forms.Textarea(attrs={"rows": 3, "placeholder": "Escreva sua mensagem..."}),
        }
