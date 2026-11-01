from django.apps import AppConfig


class VendedoresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vendedores"
    verbose_name = "Vendedores"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(_despues_de_migrar, sender=self)


def _despues_de_migrar(sender, **kwargs):
    from django.db.utils import OperationalError, ProgrammingError

    try:
        from .seed import proteger_tablas, sembrar_categorias

        sembrar_categorias()
        proteger_tablas()
    except (OperationalError, ProgrammingError):
        pass
