from django.urls import path

from . import clientes

urlpatterns = [
    path("registro/", clientes.registro_cliente, name="registro_cliente"),
    path("entrar/", clientes.entrar_cliente, name="entrar_cliente"),
    path("proveedores/", clientes.proveedores_mayor, name="proveedores_mayor"),
    path("proveedores/<slug:slug>/conectar/", clientes.conectar_proveedor, name="conectar_proveedor"),
    path("proveedores/<slug:slug>/desconectar/", clientes.desconectar_proveedor, name="desconectar_proveedor"),
    path("proveedores/<slug:slug>/lista/", clientes.lista_mayorista, name="lista_mayorista"),
    path("proveedores/<slug:slug>/pedido/", clientes.carrito_pedido, name="carrito_pedido"),
    path("proveedores/<slug:slug>/pedido/agregar/", clientes.agregar_carrito, name="agregar_carrito"),
    path("mis-proveedores/", clientes.mis_proveedores, name="mis_proveedores"),
    path("historial/", clientes.historial_comprador, name="historial_comprador"),
    path("cuenta/registro/", clientes.registro_comprador, name="registro_comprador"),
    path("cuenta/entrar/", clientes.entrar_comprador, name="entrar_comprador"),
    path("cuenta/", clientes.datos_comprador, name="datos_comprador"),
]
