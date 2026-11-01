from django.urls import path
from . import views

urlpatterns = [
    path("", views.lista_pedidos, name="lista_pedidos"),
    path("crear/<int:producto_id>/", views.crear_pedido, name="crear_pedido"),
    path("<int:pedido_id>/", views.conversacion_pedido, name="conversacion_pedido"),
    path("<int:pedido_id>/resumen.pdf", views.resumen_pedido, name="resumen_pedido"),
    path("pagar/<int:pedido_id>/", views.pagar_pedido, name="pagar_pedido"),
    path("pagar/<int:pedido_id>/resultado/", views.resultado_pago, name="resultado_pago"),
    path("wompi/evento/", views.wompi_evento, name="wompi_evento"),
]
