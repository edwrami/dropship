from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0007_servicio_pedido"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pago",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monto_cop", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("metodo", models.CharField(blank=True, max_length=40)),
                ("estado", models.CharField(choices=[("reportado", "Reportado"), ("aprobado", "Aprobado"), ("declinado", "Declinado"), ("error", "Error")], default="reportado", max_length=20)),
                ("referencia", models.CharField(blank=True, max_length=80)),
                ("comprobante", models.CharField(blank=True, max_length=120)),
                ("destino_nequi", models.CharField(blank=True, max_length=20)),
                ("wompi_id", models.CharField(blank=True, max_length=80)),
                ("origen", models.CharField(blank=True, max_length=20)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("pedido", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pago", to="pedidos.pedido")),
            ],
            options={"ordering": ["-creado"]},
        ),
    ]
