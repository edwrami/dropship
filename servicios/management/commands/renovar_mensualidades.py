from django.core.management.base import BaseCommand

from servicios.models import Oferente
from servicios.pagos import abrir_cobro_mensual


class Command(BaseCommand):
    help = "Abre el cobro de $50.000 a oferentes cuya mensualidad vence en 5 días o ya venció."

    def handle(self, *args, **options):
        abiertos = 0
        for oferente in Oferente.objects.exclude(estado="suspendido").select_related("user", "activacion"):
            cobro = abrir_cobro_mensual(oferente)
            if cobro and cobro.estado_pago == "pendiente":
                abiertos += 1
        self.stdout.write(f"Cobros de mensualidad pendientes: {abiertos}")
