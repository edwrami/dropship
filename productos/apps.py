import os
import threading
import time
import logging

from django.apps import AppConfig

log = logging.getLogger("dropship.sync")
UN_DIA = 24 * 60 * 60


def _loop_diario():
    time.sleep(8)
    while True:
        try:
            from productos.services.sync import sincronizar_catalogo
            resultado = sincronizar_catalogo()
            log.info("Barrido automático: %s", resultado)
        except Exception:
            log.exception("Error en barrido automático")
        time.sleep(UN_DIA)


class ProductosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "productos"

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        t = threading.Thread(target=_loop_diario, name="sync-catalogo", daemon=True)
        t.start()
