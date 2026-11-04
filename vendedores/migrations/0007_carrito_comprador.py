import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0008_registro_envio"),
        ("vendedores", "0006_carrito"),
    ]

    operations = [
        migrations.CreateModel(
            name="CarritoComprador",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("comprador", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="carrito", to="vendedores.comprador")),
            ],
        ),
        migrations.CreateModel(
            name="CarritoCompradorLinea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("carrito", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lineas", to="vendedores.carritocomprador")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="productos.producto")),
            ],
        ),
        migrations.AddConstraint(
            model_name="carritocompradorlinea",
            constraint=models.UniqueConstraint(fields=("carrito", "producto"), name="carrito_comprador_producto"),
        ),
    ]
