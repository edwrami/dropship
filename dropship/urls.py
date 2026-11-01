from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("vendedores/", include("vendedores.urls")),
    path("clientes/", include("vendedores.clientes_urls")),
    path("", include("productos.urls")),
    path("pedidos/", include("pedidos.urls")),
]
