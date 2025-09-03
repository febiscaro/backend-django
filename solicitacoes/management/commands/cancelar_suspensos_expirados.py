from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from solicitacoes.models import Chamado


class Command(BaseCommand):
    help = "Cancela chamados com status SUSPENSO há 5 dias ou mais (mantém 'suspenso_em' como histórico)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra quais seriam cancelados, sem salvar alterações.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Processa no máximo N chamados (útil para lotes).",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        limit = options.get("limit")
        agora = timezone.now()
        limite_data = agora - timedelta(days=5)

        # Seleciona chamados suspensos com prazo expirado
        qs_base = Chamado.objects.filter(
            status=Chamado.Status.SUSPENSO,
            suspenso_em__isnull=False,
            suspenso_em__lte=limite_data,
        ).order_by("suspenso_em")

        total_candidatos = qs_base.count()
        if total_candidatos == 0:
            self.stdout.write(self.style.SUCCESS("Nenhum chamado para cancelar."))
            return

        if limit:
            qs = qs_base[:limit]
        else:
            qs = qs_base

        ids = list(qs.values_list("id", flat=True))

        if dry_run:
            self.stdout.write(
                f"[DRY-RUN] {len(ids)} chamado(s) seria(m) cancelado(s): {ids}"
            )
            return

        # Atualiza em lote (mantém 'suspenso_em' como histórico)
        atualizados = Chamado.objects.filter(id__in=ids).update(
            status=Chamado.Status.CANCELADO,
            atualizado_em=agora,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cancelados {atualizados} chamado(s). (Candidatos totais: {total_candidatos})"
            )
        )
