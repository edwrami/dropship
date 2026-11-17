from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendedores", "0008_ficha_tienda"),
    ]

    operations = [
        migrations.AddField(model_name="vendedor", name="lat", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="vendedor", name="lng", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="vendedor", name="paga_flete", field=models.CharField(default="comprador", max_length=20)),
        migrations.AddField(model_name="clientetienda", name="lat", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="clientetienda", name="lng", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="comprador", name="lat", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="comprador", name="lng", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
    ]
