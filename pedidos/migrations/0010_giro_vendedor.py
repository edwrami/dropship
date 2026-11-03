from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0009_pagos_anteriores"),
    ]

    operations = [
        migrations.AddField(
            model_name="cuentaplataforma",
            name="payouts_account_id",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="cuentaplataforma",
            name="payouts_api_key",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="cuentaplataforma",
            name="payouts_user_id",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.CreateModel(
            name="Giro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monto_cop", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("comision_cop", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("destino_nequi", models.CharField(blank=True, max_length=20)),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente de giro"), ("sin_datos", "Faltan datos del vendedor"), ("enviado", "Enviado a Wompi"), ("pagado", "Llegó al Nequi del vendedor"), ("rechazado", "Rechazado")], default="pendiente", max_length=20)),
                ("payout_id", models.CharField(blank=True, max_length=80)),
                ("detalle", models.CharField(blank=True, max_length=300)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("pedido", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="giro", to="pedidos.pedido")),
            ],
            options={"ordering": ["-creado"]},
        ),
    ]
