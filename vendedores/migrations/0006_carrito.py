import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0008_registro_envio"),
        ("vendedores", "0005_registro_envio"),
    ]

    operations = [
        migrations.CreateModel(
            name="Carrito",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="carritos", to="vendedores.clientetienda")),
                ("proveedor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="carritos", to="vendedores.vendedor")),
            ],
        ),
        migrations.CreateModel(
            name="CarritoLinea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("carrito", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lineas", to="vendedores.carrito")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="productos.producto")),
            ],
        ),
        migrations.AddConstraint(
            model_name="carrito",
            constraint=models.UniqueConstraint(fields=("cliente", "proveedor"), name="carrito_cliente_proveedor"),
        ),
        migrations.AddConstraint(
            model_name="carritolinea",
            constraint=models.UniqueConstraint(fields=("carrito", "producto"), name="carrito_linea_producto"),
        ),
    ]
