from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import Bloqueo, Cita, Horario


def duracion_cita(especialidad=None, oferente=None):
    if especialidad and especialidad.modo_tiempo == "cita":
        minutos = int(especialidad.duracion_minutos or 60)
        return timedelta(minutes=max(minutos, 15))
    minutos = int((oferente.duracion_minutos if oferente else 60) or 60)
    return timedelta(minutes=max(minutos, 15))


def duracion_largo(especialidad, cantidad):
    cantidad = max(int(cantidad or 1), 1)
    if especialidad and especialidad.modo_tiempo == "semana":
        return timedelta(days=7 * cantidad)
    return timedelta(days=cantidad)


def citas_que_ocupan(oferente, desde, hasta):
    limite = timezone.now() - timedelta(minutes=25)
    return Cita.objects.filter(
        oferente=oferente,
        inicio__lt=hasta,
        fin__gt=desde,
    ).exclude(
        estado_pago="declinado",
    ).exclude(
        estado_pago="error",
    ).exclude(
        estado_pago="pendiente",
        creado__lt=limite,
    )


def bloqueado(oferente, inicio, fin):
    return Bloqueo.objects.filter(oferente=oferente, inicio__lt=fin, fin__gt=inicio).exists()


def hueco_libre(oferente, inicio, fin, especialidad=None):
    if inicio < timezone.now():
        return False
    if bloqueado(oferente, inicio, fin):
        return False
    modo = especialidad.modo_tiempo if especialidad else "cita"
    if modo == "cita":
        dia = inicio.weekday()
        hora = Horario.objects.filter(oferente=oferente, dia=dia, activo=True).first()
        if not hora:
            return False
        local_inicio = timezone.localtime(inicio)
        local_fin = timezone.localtime(fin)
        if local_inicio.time() < hora.abre:
            return False
        if local_fin.time() > hora.cierra:
            return False
    return not citas_que_ocupan(oferente, inicio, fin).exists()


def huecos_dia(oferente, fecha, especialidad=None):
    hora = Horario.objects.filter(oferente=oferente, dia=fecha.weekday(), activo=True).first()
    if not hora:
        return []
    paso = duracion_cita(especialidad, oferente)
    tz = timezone.get_current_timezone()
    cursor = timezone.make_aware(datetime.combine(fecha, hora.abre), tz)
    fin_jornada = timezone.make_aware(datetime.combine(fecha, hora.cierra), tz)
    ahora = timezone.now()
    libres = []
    ocupados = []
    while cursor + paso <= fin_jornada:
        fin = cursor + paso
        item = {"inicio": cursor, "fin": fin}
        if cursor < ahora:
            item["estado"] = "pasado"
        elif bloqueado(oferente, cursor, fin):
            item["estado"] = "bloqueado"
        elif citas_que_ocupan(oferente, cursor, fin).exists():
            item["estado"] = "ocupado"
        else:
            item["estado"] = "libre"
            if cursor >= ahora:
                libres.append(cursor)
        ocupados.append(item)
        cursor = fin
    return libres, ocupados


def huecos_proximos(oferente, especialidad=None, dias=14):
    hoy = timezone.localdate()
    salida = []
    for i in range(dias):
        fecha = hoy + timedelta(days=i)
        libres, _todos = huecos_dia(oferente, fecha, especialidad)
        if libres:
            salida.append((fecha, libres))
    return salida


def espacios_panel(oferente, dias=14, especialidad=None):
    hoy = timezone.localdate()
    salida = []
    for i in range(dias):
        fecha = hoy + timedelta(days=i)
        _libres, todos = huecos_dia(oferente, fecha, especialidad)
        if todos:
            salida.append((fecha, todos))
    return salida


def dias_largos_libres(oferente, especialidad, dias=60):
    hoy = timezone.localdate()
    tz = timezone.get_current_timezone()
    cantidad = 1
    paso = duracion_largo(especialidad, cantidad)
    salida = []
    for i in range(dias):
        fecha = hoy + timedelta(days=i)
        inicio = timezone.make_aware(datetime.combine(fecha, time(8, 0)), tz)
        fin = inicio + paso
        if hueco_libre(oferente, inicio, fin, especialidad):
            salida.append(fecha)
    return salida
