from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Desativado: não cancela mais chamados suspensos automaticamente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Sem efeito (desativado).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Sem efeito (desativado).",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "Comando desativado: nenhum chamado suspenso foi cancelado."
            )
        )
