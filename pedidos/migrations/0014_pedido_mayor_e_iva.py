import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0013_registro_envio"),
        ("productos", "0008_registro_envio"),
    ]

    operations = [
        migrations.AddField(
            model_name="cuentaplataforma",
            name="comision_detalle_pct",
            field=models.DecimalField(decimal_places=2, default=10, max_digits=5),
        ),
        migrations.AddField(
            model_name="cuentaplataforma",
            name="comision_mayor_pct",
            field=models.DecimalField(decimal_places=2, default=5, max_digits=5),
        ),
        migrations.AddField(
            model_name="pedido",
            name="es_mayor",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="pedido",
            name="factura_iva",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="pedido",
            name="iva_cop",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="pedido",
            name="iva_pct",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="pedido",
            name="subtotal_cop",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.CreateModel(
            name="LineaPedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=300)),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("precio_unitario", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("modo_envio", models.CharField(blank=True, max_length=20)),
                ("envio_cop", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("subtotal_cop", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("pedido", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lineas", to="pedidos.pedido")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="productos.producto")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
