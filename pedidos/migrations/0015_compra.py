import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0014_pedido_mayor_e_iva"),
        ("vendedores", "0007_carrito_comprador"),
    ]

    operations = [
        migrations.CreateModel(
            name="Compra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("referencia_pago", models.CharField(blank=True, max_length=80, unique=True)),
                ("monto_cop", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("estado_pago", models.CharField(choices=[("pendiente", "Pendiente"), ("reportado", "Cliente reportó el pago"), ("aprobado", "Aprobado"), ("declinado", "Declinado"), ("error", "Error")], default="pendiente", max_length=20)),
                ("cliente_email", models.EmailField(blank=True, max_length=254)),
                ("clave_contacto", models.CharField(blank=True, max_length=64)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("comprador", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="compras", to="vendedores.comprador")),
            ],
            options={"ordering": ["-creado"]},
        ),
        migrations.AddField(
            model_name="pedido",
            name="compra",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pedidos", to="pedidos.compra"),
        ),
    ]
