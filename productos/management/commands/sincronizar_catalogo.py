from django.core.management.base import BaseCommand
from productos.services.sync import sincronizar_catalogo


class Command(BaseCommand):
    help = "Busca productos nuevos, calcula margen y elimina los que ya no existen."

    def handle(self, *args, **options):
        res = sincronizar_catalogo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Nuevos: {res['nuevos']} | Actualizados: {res['actualizados']} | "
                f"Fuera de línea: {res['eliminados']}"
            )
        )
