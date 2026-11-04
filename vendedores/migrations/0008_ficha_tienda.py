from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendedores", "0007_carrito_comprador"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendedor",
            name="frase",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="vendedor",
            name="horario",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="vendedor",
            name="logo_url",
            field=models.URLField(blank=True, max_length=800),
        ),
        migrations.AddField(
            model_name="vendedor",
            name="logo_ruta",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
