from django.apps import AppConfig


class ServiciosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "servicios"
    verbose_name = "Servicios"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(_despues, sender=self)


def _despues(sender, **kwargs):
    from django.db.utils import OperationalError, ProgrammingError

    try:
        from .catalogo import sembrar_catalogo

        sembrar_catalogo()
    except (OperationalError, ProgrammingError):
        pass
