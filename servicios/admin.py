from django.contrib import admin

from .models import (
    Bloqueo, Cita, Cobertura, Comentario, Consulta, Especialidad, FotoTrabajo, Horario,
    MensajeConsulta, Oferente, PagoActivacion, PagoExtra,
)


@admin.register(Oferente)
class OferenteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "oficio", "ciudad", "estado", "precio_cop")
    list_filter = ("estado", "rubro", "departamento")
    search_fields = ("nombre", "responsable", "ciudad")


admin.site.register(Horario)
admin.site.register(FotoTrabajo)
admin.site.register(PagoActivacion)
admin.site.register(PagoExtra)
admin.site.register(Cobertura)
admin.site.register(Especialidad)
admin.site.register(Bloqueo)
admin.site.register(Cita)
admin.site.register(Consulta)
admin.site.register(MensajeConsulta)
admin.site.register(Comentario)
