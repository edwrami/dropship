from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0005_mayoristas_tiendas"),
    ]

    operations = [
        migrations.AddField(
            model_name="producto",
            name="precio_promo_cop",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="producto",
            name="promo_hasta",
            field=models.DateField(blank=True, null=True),
        ),
    ]
