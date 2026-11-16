from .oficios import OFICIOS, RUBROS, oficio_nombre as oficio_nombre_seed, rubro_nombre as rubro_nombre_seed


def sembrar_catalogo(forzar=False):
    from .models import OficioCatalogo, RubroCatalogo

    if not forzar and OficioCatalogo.objects.exists():
        existentes = set(OficioCatalogo.objects.values_list("clave", flat=True))
        faltan = False
        for clave, lista in OFICIOS.items():
            for oclave, _onombre in lista:
                if oclave not in existentes:
                    faltan = True
                    break
            if faltan:
                break
        if not faltan:
            return

    for i, (clave, nombre) in enumerate(RUBROS):
        rubro, _ = RubroCatalogo.objects.get_or_create(
            clave=clave, defaults={"nombre": nombre, "orden": i, "activo": True},
        )
        for j, (oclave, onombre) in enumerate(OFICIOS.get(clave) or []):
            OficioCatalogo.objects.get_or_create(
                rubro=rubro, clave=oclave,
                defaults={"nombre": onombre, "orden": j, "activo": True},
            )


def rubros_choices():
    from .models import RubroCatalogo

    try:
        filas = list(RubroCatalogo.objects.filter(activo=True).order_by("orden", "nombre"))
    except Exception:
        filas = []
    if filas:
        return [(r.clave, r.nombre) for r in filas]
    return list(RUBROS)


def oficios_mapa():
    from .models import OficioCatalogo

    try:
        filas = OficioCatalogo.objects.filter(activo=True, rubro__activo=True).select_related("rubro")
        mapa = {}
        for ofi in filas:
            mapa.setdefault(ofi.rubro.clave, []).append((ofi.clave, ofi.nombre))
        if mapa:
            return mapa
    except Exception:
        pass
    return {k: list(v) for k, v in OFICIOS.items()}


def oficio_nombre(rubro, oficio):
    from .models import OficioCatalogo

    try:
        hallado = OficioCatalogo.objects.filter(clave=oficio, activo=True).select_related("rubro").first()
        if hallado:
            return hallado.nombre
    except Exception:
        pass
    return oficio_nombre_seed(rubro, oficio)


def rubro_nombre(rubro):
    from .models import RubroCatalogo

    try:
        hallado = RubroCatalogo.objects.filter(clave=rubro).first()
        if hallado:
            return hallado.nombre
    except Exception:
        pass
    return rubro_nombre_seed(rubro)
