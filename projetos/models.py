import uuid
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.conf import settings
from django.core.exceptions import ValidationError


class CostCenter(models.Model):
    """
    Cada Centro de Custo representa um cliente.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identificação
    nome = models.CharField("Nome do Centro de Custo", max_length=150, unique=True)
    codigo = models.CharField("Código interno", max_length=30, unique=True)
    cliente = models.CharField("Cliente (Razão/Nome Fantasia)", max_length=150, blank=True)
    ativo = models.BooleanField("Ativo", default=True)

    # Contato (opcional)
    contato_nome = models.CharField("Contato principal", max_length=100, blank=True)
    contato_email = models.EmailField("E-mail do contato", blank=True)
    contato_telefone = models.CharField("Telefone do contato", max_length=30, blank=True)

    # Contrato
    contrato_inicio = models.DateField("Início do contrato", null=True, blank=True)
    contrato_fim    = models.DateField("Fim do contrato", null=True, blank=True)

    # Imagem de fundo do card (opcional)
    background_image = models.ImageField(
        "Imagem de fundo do card",
        upload_to="centros_bg/",
        null=True, blank=True
    )


    # Orçamento e horas
    orcamento_total = models.DecimalField(
        "Orçamento total (R$)", max_digits=14, decimal_places=2,
        null=True, blank=True, validators=[MinValueValidator(0)]
    )
    horas_previstas = models.DecimalField(
        "Horas-homem previstas", max_digits=9, decimal_places=2,
        null=True, blank=True, validators=[MinValueValidator(0)]
    )

    # Auditoria
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Centro de Custo"
        verbose_name_plural = "Centros de Custo"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.codigo})"

    # Helper: checa se um e-mail é permitido por domínio
    def is_email_domain_allowed(self, email: str) -> bool:
        """
        Se houver domínios cadastrados para este centro, exige que o e-mail pertença a um deles.
        Se não houver nenhum domínio cadastrado, considera permitido (libera).
        """
        if not email or "@" not in email:
            return False
        domain = email.rsplit("@", 1)[-1].lower()
        qs = self.dominios_permitidos.filter(ativo=True).values_list("dominio", flat=True)
        if not qs.exists():
            return True
        return domain in set(qs)


class AllowedDomain(models.Model):
    """
    Domínios de e-mail permitidos para cadastro/acesso de usuários deste centro.
    Ex.: 'empresa.com.br'
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    centro = models.ForeignKey(
        CostCenter, on_delete=models.CASCADE, related_name="dominios_permitidos"
    )
    dominio = models.CharField(
        "Domínio de e-mail", max_length=255,
        validators=[RegexValidator(
            regex=r"^[a-z0-9.-]+\.[a-z]{2,}$",
            message="Informe um domínio válido, ex.: empresa.com.br"
        )]
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Domínio permitido"
        verbose_name_plural = "Domínios permitidos"
        unique_together = [("centro", "dominio")]
        indexes = [
            models.Index(fields=["centro", "ativo"]),
        ]

    def save(self, *args, **kwargs):
        if self.dominio:
            self.dominio = self.dominio.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.dominio} ({self.centro})"




class CostCenterMember(models.Model):
    """
    Vínculo entre um usuário e um Centro de Custo, com papel.
    Usaremos esse model nas views para decidir quem pode ver/criar/editar.
    """
    class Role(models.TextChoices):
        GESTOR = "GESTOR", "Gestor"        # pode criar/editar centros/tarefas
        COLAB  = "COLAB",  "Colaborador"   # vê e executa tarefas do centro

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    centro = models.ForeignKey(
        CostCenter, on_delete=models.CASCADE, related_name="membros"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="centros_membro"
    )

    papel = models.CharField("Papel", max_length=10, choices=Role.choices, default=Role.COLAB)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Membro do Centro"
        verbose_name_plural = "Membros do Centro"
        unique_together = [("centro", "usuario")]           # impede duplicar o mesmo usuário no mesmo centro
        indexes = [
            models.Index(fields=["centro", "papel"]),       # acelera filtros por centro/papel
        ]

    def __str__(self):
        return f"{self.usuario} em {self.centro} ({self.get_papel_display()})"






# Aqui eu começo o model da pagina onde a gestão crias as tarefas, a ideia é fazer estilo Kambam

class Project(models.Model):
    """
    Projeto dentro de um Centro de Custo.
    Vai aparecer como 'lista suspensa' ao criar a tarefa.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    centro = models.ForeignKey("projetos.CostCenter", on_delete=models.CASCADE, related_name="projetos")
    nome = models.CharField("Nome do projeto", max_length=120)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"
        unique_together = [("centro", "nome")]
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} — {self.centro.nome}"


# --- Máscara de recorrência (dias da semana) -------------------------------
# Representação leve (funciona no SQLite): bitmask 0..127
# 2^0=Seg, 2^1=Ter, 2^2=Qua, 2^3=Qui, 2^4=Sex, 2^5=Sáb, 2^6=Dom

DOW = {
    "MON": 1 << 0,  # Seg
    "TUE": 1 << 1,  # Ter
    "WED": 1 << 2,  # Qua
    "THU": 1 << 3,  # Qui
    "FRI": 1 << 4,  # Sex
    "SAT": 1 << 5,  # Sáb
    "SUN": 1 << 6,  # Dom
}
DOW_ORDER = [("MON","Seg"),("TUE","Ter"),("WED","Qua"),("THU","Qui"),("FRI","Sex"),("SAT","Sáb"),("SUN","Dom")]


class Task(models.Model):
    """
    Tarefa criada pelo gestor para colaboradores executarem no Centro de Custo.
    """

    class Status(models.TextChoices):
        ABERTA       = "OPEN",  "Aberta"         # criada, ainda não executada
        EM_ANDAMENTO = "DOING", "Em andamento"   # algum colaborador já lançou atividade
        PAUSADA      = "PAUSE", "Pausada"        # gestor pausou; some da tela do executor
        EM_AVALIACAO = "REVIEW","Em avaliação"   # colaborador finalizou; gestor valida
        CONCLUIDA    = "DONE",  "Concluída"      # gestor validou

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Contexto
    centro  = models.ForeignKey("projetos.CostCenter", on_delete=models.CASCADE, related_name="tarefas")
    projeto = models.ForeignKey("projetos.Project", on_delete=models.PROTECT, related_name="tarefas")

    # Dados principais da tarefa
    nome = models.CharField("Nome da tarefa", max_length=200)       # texto
    orientacoes = models.TextField("Orientações", blank=True)       # instruções

    # Pessoas autorizadas a lançar atividades (multi-seleção)
    autorizados = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="tarefas_autorizadas",
        help_text="Usuários que podem registrar atividades nesta tarefa."
    )

    # Planejamento
    data_inicio_prevista = models.DateField(null=True, blank=True)  # data início previsto
    data_fim_prevista    = models.DateField(null=True, blank=True)  # data fim previsto
    horas_homem_previstas = models.DecimalField(                    # HH previstas
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Recorrência diária
    recorrencia_dias = models.PositiveSmallIntegerField(            # dias da semana (bitmask)
        "Dias da semana (máscara)", default=0,
        help_text="Seg=1, Ter=2, Qua=4, Qui=8, Sex=16, Sáb=32, Dom=64 (some para combinar)."
    )
    hora_publicacao = models.TimeField(                             # horário que aparece pro colaborador
        "Horário para aparecer", null=True, blank=True
    )
    encerra_no_fim_do_dia = models.BooleanField(                    # encerra 23:59 do mesmo dia
        "Encerrar às 23:59 do mesmo dia", default=True
    )

    # Status geral
    status = models.CharField("Status", max_length=10, choices=Status.choices, default=Status.ABERTA)

    # Auditoria
    criado_por = models.ForeignKey(                                 # gestor/superuser que criou
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tarefas_criadas"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tarefa"
        verbose_name_plural = "Tarefas"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["centro", "projeto", "status"]),
        ]

    # -------- Helpers p/ recorrência --------
    def set_dias(self, keys):
        """Define dias a partir de ['MON','WED',...]"""
        mask = 0
        for k in keys:
            mask |= DOW.get(k, 0)
        self.recorrencia_dias = mask

    def get_dias_labels(self):
        """Retorna ['Seg','Qua',...] dos dias marcados."""
        out = []
        for key, label in DOW_ORDER:
            if self.recorrencia_dias & DOW[key]:
                out.append(label)
        return out

    # -------- Regras de consistência --------
    def clean(self):
        # fim não pode ser antes do início
        if self.data_inicio_prevista and self.data_fim_prevista and self.data_fim_prevista < self.data_inicio_prevista:
            raise ValidationError({"data_fim_prevista": "Fim previsto não pode ser antes do início."})
        # projeto deve pertencer ao mesmo centro
        if self.projeto_id and self.centro_id and self.projeto.centro_id != self.centro_id:
            raise ValidationError({"projeto": "O projeto escolhido não pertence a este Centro de Custo."})

    def __str__(self):
        return f"{self.nome} ({self.get_status_display()})"