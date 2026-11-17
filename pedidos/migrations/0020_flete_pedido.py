from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0019_wompi_privada"),
    ]

    operations = [
        migrations.AddField(model_name="pedido", name="flete_cop", field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.AddField(model_name="pedido", name="flete_km", field=models.DecimalField(decimal_places=1, default=0, max_digits=8)),
        migrations.AddField(model_name="pedido", name="flete_paga", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="pedido", name="flete_vendedor_cop", field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
    ]
