from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pedidos", "0015_compra"),
    ]

    operations = [
        migrations.AddField(
            model_name="reclamo",
            name="decision",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Sin decisión"),
                    ("reponer", "Reponer el producto"),
                    ("devolver", "Devolver el dinero"),
                    ("rechazar", "Rechazar el reclamo"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="reclamo",
            name="nota_cierre",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="reclamo",
            name="cerrado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="Aviso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=160)),
                ("texto", models.TextField()),
                ("url", models.CharField(blank=True, max_length=300)),
                ("leido", models.BooleanField(db_index=True, default=False)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="avisos", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-creado", "-id"]},
        ),
    ]
