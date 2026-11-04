from django.urls import path

from vendedores.paginas import pagina_legal
from vendedores.views import estado_tienda, tienda_publica

from . import views

urlpatterns = [
    path("", views.lista_productos, name="lista_productos"),
    path("legal/<slug:slug>/", pagina_legal, name="pagina_legal"),
    path("facebook/", views.carrusel_facebook, name="carrusel_facebook"),
    path("agregar/", views.agregar_producto, name="agregar_producto"),
    path("tienda/<slug:slug>/", tienda_publica, name="tienda_publica"),
    path("tienda/<slug:slug>/estado/", estado_tienda, name="estado_tienda"),
    path("producto/<int:pk>/", views.detalle_producto, name="detalle_producto"),
    path("producto/<int:pk>/estado/", views.estado_producto, name="estado_producto"),
]
