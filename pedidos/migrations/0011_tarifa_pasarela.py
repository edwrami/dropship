from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0010_giro_vendedor"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="tarifa_pasarela_cop",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
