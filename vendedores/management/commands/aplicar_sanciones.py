from django.core.management.base import BaseCommand

from vendedores.services import aplicar_sanciones


class Command(BaseCommand):
    help = "Retira de la página a quien no liquidó la comisión del 10%."

    def handle(self, *args, **options):
        n = aplicar_sanciones()
        self.stdout.write(self.style.SUCCESS(f"Tiendas retiradas: {n}"))
