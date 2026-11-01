from django.db import connection
from django.utils.text import slugify

from .categorias_data import ARBOL
from .models import Categoria


def sembrar_categorias():
    for i, (padre_nombre, hijos) in enumerate(ARBOL):
        slug_p = slugify(padre_nombre)[:160]
        padre, _ = Categoria.objects.get_or_create(
            slug=slug_p,
            defaults={"nombre": padre_nombre, "orden": i},
        )
        if padre.nombre != padre_nombre or padre.orden != i or padre.padre_id:
            padre.nombre = padre_nombre
            padre.orden = i
            padre.padre = None
            padre.save(update_fields=["nombre", "orden", "padre"])
        for j, hijo in enumerate(hijos):
            slug_h = slugify(f"{padre_nombre}-{hijo}")[:160]
            cat, _ = Categoria.objects.get_or_create(
                slug=slug_h,
                defaults={"nombre": hijo, "padre": padre, "orden": j},
            )
            if cat.padre_id != padre.id or cat.nombre != hijo or cat.orden != j:
                cat.nombre = hijo
                cat.padre = padre
                cat.orden = j
                cat.save(update_fields=["nombre", "padre", "orden"])
    return Categoria.objects.filter(padre__isnull=False).count()


def proteger_tablas():
    """El anon key de Supabase no puede leer teléfonos, pedidos ni usuarios."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DO $$
            DECLARE r record;
            BEGIN
              FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
              LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
                EXECUTE format(
                  'REVOKE ALL ON TABLE public.%I FROM anon, authenticated',
                  r.tablename
                );
              END LOOP;
            END $$;
            """
        )
        cursor.execute(
            "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated"
        )
        cursor.execute(
            """
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON TABLES FROM anon, authenticated
            """
        )
        cursor.execute(
            """
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL ON SEQUENCES FROM anon, authenticated
            """
        )
