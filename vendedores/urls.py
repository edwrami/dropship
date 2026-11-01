from django.urls import path

from . import views

urlpatterns = [
    path("registro/", views.registro, name="registro_vendedor"),
    path("entrar/", views.entrar, name="entrar_vendedor"),
    path("salir/", views.salir, name="salir_vendedor"),
    path("panel/", views.panel, name="panel_vendedor"),
    path("datos/", views.datos, name="datos_vendedor"),
    path("producto/nuevo/", views.producto_form, name="nuevo_producto"),
    path("producto/<int:pk>/editar/", views.producto_form, name="editar_producto"),
    path("producto/<int:pk>/ocultar/", views.ocultar_producto, name="ocultar_producto"),
    path("liquidar/", views.liquidar, name="liquidar_comision"),
    path("pedido/<int:pk>/cancelar/", views.cancelar_pedido, name="cancelar_pedido_vendedor"),
]
