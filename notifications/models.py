from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "E-mail"

    # tipo genérico (para reuso entre apps): ex. "ticket.created", "ticket.reply", "ticket.status"
    kind = models.CharField(max_length=64)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.EMAIL)

    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)

    # rastreio
    is_sent = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    # referência cruzada opcional
    ref_app = models.CharField(max_length=50, blank=True)    # ex: "solicitacoes"
    ref_model = models.CharField(max_length=50, blank=True)  # ex: "Chamado"
    ref_pk = models.CharField(max_length=50, blank=True)     # ex: "123"

    class Meta:
        indexes = [models.Index(fields=["kind", "created_at"])]

    def __str__(self):
        status = "sent" if self.is_sent else "pending"
        return f"[{self.kind}] -> {self.to_email} ({status})"


class NotificationOptOut(models.Model):
    """Opt-out por e-mail e/ou por tipo (kind). kind vazio => opt-out global."""
    email = models.EmailField()
    kind = models.CharField(max_length=64, blank=True)  # "" = global

    class Meta:
        unique_together = ("email", "kind")

    def __str__(self):
        return f"{self.email} (kind={self.kind or 'GLOBAL'})"
