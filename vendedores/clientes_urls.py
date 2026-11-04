from django.urls import path

from . import clientes

urlpatterns = [
    path("registro/", clientes.registro_cliente, name="registro_cliente"),
    path("entrar/", clientes.entrar_cliente, name="entrar_cliente"),
    path("proveedores/", clientes.proveedores_mayor, name="proveedores_mayor"),
    path("proveedores/<slug:slug>/conectar/", clientes.conectar_proveedor, name="conectar_proveedor"),
    path("proveedores/<slug:slug>/desconectar/", clientes.desconectar_proveedor, name="desconectar_proveedor"),
    path("proveedores/<slug:slug>/lista/", clientes.lista_mayorista, name="lista_mayorista"),
    path("mis-proveedores/", clientes.mis_proveedores, name="mis_proveedores"),
    path("historial/", clientes.historial_comprador, name="historial_comprador"),
]
