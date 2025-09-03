from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone





# =========================
# Tipos e Perguntas
# =========================

class TipoSolicitacao(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(default=timezone.now)

    # Lista de setores autorizados (vazio => visível para todos)
    setores_permitidos = models.CharField(
        max_length=300,
        blank=True,
        help_text="Nomes dos setores separados por ';' (ex.: RH; Financeiro; TI). Vazio = todos."
    )

    class Meta:
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

    # Helpers de setores
    def setores_lista(self):
        s = (self.setores_permitidos or '').replace('\r', '').replace('\n', '')
        return [t.strip().lower() for t in s.split(';') if t.strip()]

    def visivel_para(self, user) -> bool:
        if not self.ativo:
            return False
        permitidos = self.setores_lista()
        if not permitidos:
            return True
        user_setor = (getattr(user, "setor", "") or "").strip().lower()
        return user_setor in permitidos


class PerguntaTipoSolicitacao(models.Model):
    class TipoCampo(models.TextChoices):
        TEXTO_CURTO = "text", "Texto curto"
        TEXTO_LONGO = "textarea", "Texto longo"
        INTEIRO = "int", "Número inteiro"
        DECIMAL = "decimal", "Número decimal"
        DATA = "date", "Data"
        DATA_HORA = "datetime", "Data e hora"
        BOOLEANO = "bool", "Sim/Não"
        ESCOLHA = "choice", "Escolha única"
        MULTIESCOLHA = "multichoice", "Múltipla escolha"
        ARQUIVO = "file", "Arquivo"

    tipo = models.ForeignKey(TipoSolicitacao, on_delete=models.CASCADE, related_name="perguntas")
    texto = models.CharField(max_length=255)
    tipo_campo = models.CharField(max_length=20, choices=TipoCampo.choices, default=TipoCampo.TEXTO_CURTO)
    obrigatoria = models.BooleanField(default=True)
    ajuda = models.CharField(max_length=255, blank=True)
    ordem = models.PositiveIntegerField(default=1)
    opcoes = models.CharField(
        max_length=800, blank=True,
        help_text="Para escolha/múltipla escolha, separe as opções por ';'."
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self) -> str:
        return f"{self.tipo.nome} - {self.texto[:40]}"

    @property
    def opcoes_lista(self):
        s = (self.opcoes or '').replace('\r', '').replace('\n', '')
        return [o.strip() for o in s.split(';') if o.strip()]


# =========================
# Chamado
# =========================

def anexo_adm_upload_path(instance, filename):
    """
    Anexos administrativos vinculados ao próprio Chamado.
    Se ainda não houver PK, salva em uma pasta 'tmp' (situação rara).
    """
    cid = instance.pk or "tmp"
    return f"chamados/{cid}/adm/{filename}"


class Chamado(models.Model):
    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDO = "concluido", "Concluído"
        SUSPENSO = "suspenso", "Suspenso"
        CANCELADO = "cancelado", "Cancelado"

    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chamados", db_index=True
    )
    tipo = models.ForeignKey(TipoSolicitacao, on_delete=models.PROTECT, related_name="chamados")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTO, db_index=True)
    tratativa_adm = models.TextField(blank=True)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # quando entra em suspensão
    suspenso_em = models.DateTimeField(null=True, blank=True, db_index=True)

    # quem está atendendo (nome livre)
    atendente_nome = models.CharField(max_length=120, blank=True)

    # anexo administrativo da tratativa
    anexo_adm = models.FileField(upload_to=anexo_adm_upload_path, blank=True, null=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status", "criado_em"]),
        ]

    def __str__(self) -> str:
        return f"#{self.pk} - {self.tipo.nome} - {self.get_status_display()}"

    # ---------- Helpers de fluxo ----------
    def suspender(self):
        self.status = self.Status.SUSPENSO
        self.suspenso_em = timezone.now()

    def reabrir(self):
        self.status = self.Status.ABERTO
        self.suspenso_em = None

    @property
    def suspensao_expirada(self) -> bool:
        if self.status != self.Status.SUSPENSO or not self.suspenso_em:
            return False
        return timezone.now() >= self.suspenso_em + timedelta(days=5)

    def cancelar_por_expiracao(self):
        self.status = self.Status.CANCELADO
        # mantém suspenso_em como histórico

    @property
    def prazo_reabertura(self):
        """Data/hora limite para reabrir (5 dias após a suspensão)."""
        if not self.suspenso_em:
            return None
        return self.suspenso_em + timedelta(days=5)

    @property
    def prazo_reabertura_expirou(self) -> bool:
        """Se o prazo de 5 dias para reabrir já passou."""
        return self.suspensao_expirada

    # --------- Helpers para o template (evita chamar exists() em template) ---------
    @property
    def tem_anexo_adm(self) -> bool:
        return bool(self.anexo_adm)

    def tem_anexo_respostas(self) -> bool:
        return self.respostas.filter(valor_arquivo__isnull=False).exists()


# =========================
# Respostas do Colaborador
# =========================

def anexo_upload_path(instance, filename):
    # anexos enviados nas respostas das perguntas do chamado
    return f"chamados/{instance.chamado_id}/anexos/{filename}"


class RespostaChamado(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="respostas")
    pergunta = models.ForeignKey(PerguntaTipoSolicitacao, on_delete=models.PROTECT, related_name="respostas")

    # Para simplificar, múltipla escolha como texto separado por ";"
    valor_texto = models.TextField(blank=True)
    valor_arquivo = models.FileField(upload_to=anexo_upload_path, blank=True, null=True)

    class Meta:
        ordering = ["pergunta__ordem", "pergunta_id"]
        constraints = [
            models.UniqueConstraint(fields=["chamado", "pergunta"], name="uq_resposta_chamado_pergunta"),
        ]

    def __str__(self):
        return f"Chamado #{self.chamado_id} - {self.pergunta.texto[:40]}"


# =========================
# Vistas de Seção (Meus Chamados)
# =========================

class SecaoVista(models.Model):
    SECOES = (
        ("abertos", "Abertos"),
        ("andamento", "Em andamento"),
        ("suspensos", "Suspensos"),
        ("concluidos", "Concluídos"),
        ("cancelados", "Cancelados"),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    secao = models.CharField(max_length=20, choices=SECOES)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "secao"], name="uq_secao_vista_user_secao"),
        ]

    def __str__(self):
        return f"{self.user} - {self.secao} @ {self.last_seen:%d/%m %H:%M}"


# =========================
# Mensagens do Chamado (chat/linha do tempo)
# =========================

def mensagem_upload_path(instance, filename):
    cid = instance.chamado_id or (instance.chamado.pk if instance.chamado_id is None else "tmp")
    return f"chamados/{cid}/mensagens/{filename}"


class ChamadoMensagem(models.Model):
    PUBLICA = "publica"
    INTERNA = "interna"
    VISIBILIDADE = [(PUBLICA, "Pública"), (INTERNA, "Interna")]

    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="mensagens")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    texto = models.TextField()
    anexo = models.FileField(upload_to=mensagem_upload_path, blank=True, null=True)
    visibilidade = models.CharField(max_length=10, choices=VISIBILIDADE, default=PUBLICA)
    # mensagem|status|atualizacao|sistema
    tipo_evento = models.CharField(max_length=30, default="mensagem", blank=True)
    meta = models.JSONField(blank=True, null=True)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["chamado", "criado_em"]),
            models.Index(fields=["visibilidade"]),
        ]

    def __str__(self):
        return f"Msg #{self.pk} do Chamado #{self.chamado_id} por {self.autor}"


# =========================
# Última visualização do Chamado por usuário
# =========================

class ChamadoVista(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chamado_vistas")
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="vistas")
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "chamado"], name="uq_chamado_vista_user_chamado"),
        ]

    def __str__(self):
        return f"{self.user} viu #{self.chamado_id} em {self.last_seen:%d/%m %H:%M}"


