from django.db import migrations

ESTADOS = {"reportado", "aprobado", "declinado", "error"}


def copiar_pagos(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    Pago = apps.get_model("pedidos", "Pago")
    for pedido in Pedido.objects.exclude(estado_pago="pendiente"):
        if Pago.objects.filter(pedido_id=pedido.pk).exists():
            continue
        estado = pedido.estado_pago if pedido.estado_pago in ESTADOS else "reportado"
        origen = "wompi" if pedido.wompi_id else "historico"
        Pago.objects.create(
            pedido=pedido,
            monto_cop=pedido.monto_cop,
            metodo=(pedido.metodo_pago or "nequi")[:40],
            estado=estado,
            referencia=(pedido.referencia_pago or "")[:80],
            comprobante=(pedido.comprobante or "")[:120],
            destino_nequi=(pedido.contacto_nequi or "")[:20],
            wompi_id=(pedido.wompi_id or "")[:80],
            origen=origen[:20],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0008_pago"),
    ]

    operations = [
        migrations.RunPython(copiar_pagos, migrations.RunPython.noop),
    ]
