import json
import uuid
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from pedidos.services import wompi
from productos.services.storage import borrar_foto, extension, subir_foto
from vendedores.opciones import DEPARTAMENTOS

from .agenda import (
    dias_largos_libres,
    duracion_cita,
    duracion_largo,
    espacios_panel,
    hueco_libre,
    huecos_proximos,
)
from .alertas import avisar_agenda, avisar_consulta, avisar_mensaje_consulta
from .contacto import sin_contacto
from .forms import ComentarioForm, ContratarForm, FichaOferenteForm, RegistroOferenteForm
from .models import (
    Bloqueo,
    Cita,
    Cobertura,
    Comentario,
    Consulta,
    MensajeConsulta,
    Especialidad,
    FotoTrabajo,
    Horario,
    Oferente,
    PagoActivacion,
    PagoExtra,
    PagoMensualidad,
)
from .municipios import MUNICIPIOS
from .catalogo import oficios_mapa, rubros_choices
from .oficios import DIAS, MODOS_TIEMPO
from .pagos import (
    abrir_cobro_inscripcion,
    abrir_cobro_mensual,
    aplicar_comision_cita,
    aplicar_transaccion,
    cuota_activacion,
    cuota_mensualidad,
    cuota_primera,
    intentar_giro_servicio,
    nueva_referencia,
)


def _oferente(user):
    if not user.is_authenticated:
        return None
    try:
        return user.oferente
    except ObjectDoesNotExist:
        return None


def _publico():
    return (
        Oferente.objects.filter(estado="activo", mensualidad_hasta__gte=timezone.now())
        .annotate(nota=Avg("comentarios__estrellas"), opiniones=Count("comentarios", distinct=True))
        .prefetch_related("fotos")
    )


def lista(request):
    qs = _publico()
    q = (request.GET.get("q") or "").strip()
    rubro = (request.GET.get("rubro") or "").strip()
    oficio = (request.GET.get("oficio") or "").strip()
    ciudad = (request.GET.get("ciudad") or request.GET.get("municipio") or "").strip()
    departamento = (request.GET.get("departamento") or "").strip()
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) | Q(descripcion__icontains=q) | Q(oficio__icontains=q)
            | Q(ciudad__icontains=q) | Q(especialidades__oficio__icontains=q)
        )
    if rubro:
        qs = qs.filter(Q(rubro=rubro) | Q(especialidades__rubro=rubro, especialidades__activa=True))
    if oficio:
        qs = qs.filter(Q(oficio=oficio) | Q(especialidades__oficio=oficio, especialidades__activa=True))
    if departamento:
        qs = qs.filter(
            Q(departamento=departamento) | Q(coberturas__departamento=departamento, coberturas__activa=True)
        )
    if ciudad:
        qs = qs.filter(
            Q(ciudad__icontains=ciudad) | Q(coberturas__municipio__icontains=ciudad, coberturas__activa=True)
        )
    if request.GET.get("libres"):
        qs = qs.filter(disponible_ahora=True)
    if request.GET.get("calificados"):
        qs = qs.filter(nota__gte=4)
    if request.GET.get("satisfechos"):
        qs = qs.filter(opiniones__gte=1, nota__gte=4)
    if q or rubro or oficio or ciudad or departamento:
        qs = qs.distinct()
    return render(request, "servicios/lista.html", {
        "oferentes": qs[:120],
        "total": qs.count(),
        "rubros": rubros_choices(),
        "oficios_json": json.dumps(oficios_mapa()),
        "municipios_json": json.dumps(MUNICIPIOS),
        "departamentos": DEPARTAMENTOS,
        "cuota": cuota_activacion(),
        "mensualidad": cuota_mensualidad(),
        "primera": cuota_primera(),
    })


def detalle(request, slug):
    oferente = get_object_or_404(
        _publico().prefetch_related(
            "fotos",
            "horarios",
            "coberturas",
            "especialidades",
            "comentarios",
        ),
        slug=slug,
    )
    Oferente.objects.filter(pk=oferente.pk).update(visitas=oferente.visitas + 1)
    oferente.visitas += 1
    especialidades = oferente.especialidades.filter(activa=True)
    coberturas = oferente.coberturas.filter(activa=True)
    esp_id = request.GET.get("oficio") or ""
    especialidad = especialidades.filter(pk=esp_id).first() if str(esp_id).isdigit() else especialidades.first()
    agenda = []
    dias_largos = []
    if oferente.disponible_ahora and especialidad:
        if especialidad.modo_tiempo == "cita":
            agenda = huecos_proximos(oferente, especialidad)
        else:
            dias_largos = dias_largos_libres(oferente, especialidad)
    return render(request, "servicios/detalle.html", {
        "oferente": oferente,
        "especialidades": especialidades,
        "especialidad": especialidad,
        "coberturas": coberturas,
        "agenda": agenda,
        "dias_largos": dias_largos,
        "dias": DIAS,
        "cuota": cuota_activacion(),
    })


def registro(request):
    actual = _oferente(request.user)
    if actual:
        return redirect("panel_oferente")
    form = RegistroOferenteForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        from vendedores.cuentas import abrir_cuenta, asegurar_comprador
        user, error = abrir_cuenta(
            request, data["email"], data.get("password") or "", data.get("password2") or "",
        )
        if error:
            form.add_error("password", error)
        elif _oferente(user):
            login(request, user)
            messages.info(request, "Este correo ya tiene ficha de oferente.")
            return redirect("panel_oferente")
        else:
            with transaction.atomic():
                login(request, user)
                asegurar_comprador(user, {**data, "nombre": data["responsable"]})
                oferente = Oferente.objects.create(
                    user=user,
                    nombre=data["nombre"],
                    responsable=data["responsable"],
                    documento=data["documento"],
                    telefono=data["telefono"],
                    whatsapp=data["whatsapp"],
                    nequi=data["nequi"],
                    email=data["email"],
                    ciudad=data["ciudad"].strip(),
                    departamento=data["departamento"],
                    rubro=data["rubro"],
                    oficio=data["oficio"],
                    descripcion=data["descripcion"],
                    precio_cop=data["precio_cop"],
                    unidad=data["unidad"],
                    duracion_minutos=int(data["duracion_minutos"]),
                    acepta_terminos=True,
                    estado="pendiente_pago",
                )
                for dia in range(6):
                    Horario.objects.create(
                        oferente=oferente, dia=dia,
                        abre=time(8, 0), cierra=time(18, 0), activo=True,
                    )
                Horario.objects.create(
                    oferente=oferente, dia=6,
                    abre=time(8, 0), cierra=time(12, 0), activo=False,
                )
                Cobertura.objects.get_or_create(
                    oferente=oferente,
                    departamento=oferente.departamento,
                    municipio=oferente.ciudad,
                    defaults={"incluida": True, "activa": False},
                )
                Especialidad.objects.get_or_create(
                    oferente=oferente,
                    rubro=oferente.rubro,
                    oficio=oferente.oficio,
                    defaults={
                        "precio_cop": oferente.precio_cop,
                        "unidad": oferente.unidad,
                        "modo_tiempo": data.get("modo_tiempo") or "cita",
                        "duracion_minutos": oferente.duracion_minutos,
                        "incluida": True,
                        "activa": False,
                    },
                )
            messages.success(
                request,
                "Ficha creada. Paga $100.000 de inscripción; ese cobro incluye el primer mes. "
                "Después ERA shop te abre solo el cobro de $50.000 cada mes. Las citas pagan comisión aparte.",
            )
            return redirect("activar_oferente")
    return render(request, "servicios/registro.html", {
        "form": form,
        "oficios_json": json.dumps(oficios_mapa()),
        "municipios_json": json.dumps(MUNICIPIOS),
        "cuota": cuota_activacion(),
        "mensualidad": cuota_mensualidad(),
        "primera": cuota_primera(),
        "otra_cuenta": request.user.is_authenticated,
    })


def entrar(request):
    from vendedores import cuentas
    return cuentas.entrar_cuenta(request)


def salir(request):
    logout(request)
    return redirect("lista_servicios")


@login_required(login_url="entrar_cuenta")
def panel(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    abrir_cobro_mensual(oferente)
    citas = oferente.citas.select_related("pago", "giro", "especialidad").all()[:80]
    return render(request, "servicios/panel.html", {
        "oferente": oferente,
        "citas": citas,
        "fotos": oferente.fotos.all(),
        "horarios": oferente.horarios.all(),
        "coberturas": oferente.coberturas.all(),
        "especialidades": oferente.especialidades.all(),
        "consultas": oferente.consultas.select_related("especialidad")[:30],
        "cuota": cuota_activacion(),
        "mensualidad": cuota_mensualidad(),
        "primera": cuota_primera(),
        "aparece": oferente.visible,
        "dias": DIAS,
    })


@login_required(login_url="entrar_cuenta")
def ficha(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    inicial = {
        "nombre": oferente.nombre,
        "telefono": oferente.telefono,
        "whatsapp": oferente.whatsapp,
        "nequi": oferente.nequi,
        "ciudad": oferente.ciudad,
        "departamento": oferente.departamento,
        "rubro": oferente.rubro,
        "oficio": oferente.oficio,
        "descripcion": oferente.descripcion,
        "precio_cop": int(oferente.precio_cop),
        "unidad": oferente.unidad,
        "duracion_minutos": str(oferente.duracion_minutos),
        "disponible_ahora": oferente.disponible_ahora,
    }
    form = FichaOferenteForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        for campo in ("nombre", "telefono", "whatsapp", "nequi", "ciudad", "departamento", "rubro", "oficio", "descripcion", "precio_cop", "unidad"):
            setattr(oferente, campo, data[campo])
        oferente.duracion_minutos = int(data["duracion_minutos"])
        oferente.disponible_ahora = bool(data.get("disponible_ahora"))
        oferente.save()
        messages.success(request, "Ficha actualizada.")
        return redirect("panel_oferente")
    return render(request, "servicios/ficha.html", {
        "form": form,
        "oferente": oferente,
        "oficios_json": json.dumps(oficios_mapa()),
    })


@login_required(login_url="entrar_cuenta")
def horarios(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    actuales = {h.dia: h for h in oferente.horarios.all()}
    filas = []
    for dia, nombre in DIAS:
        h = actuales.get(dia)
        filas.append({
            "dia": dia,
            "nombre": nombre,
            "activo": h.activo if h else False,
            "abre": (h.abre.strftime("%H:%M") if h else "08:00"),
            "cierra": (h.cierra.strftime("%H:%M") if h else "18:00"),
        })
    if request.method == "POST":
        for dia, nombre in DIAS:
            activo = request.POST.get(f"activo_{dia}") == "1"
            abre = request.POST.get(f"abre_{dia}") or "08:00"
            cierra = request.POST.get(f"cierra_{dia}") or "18:00"
            try:
                h_abre = datetime.strptime(abre, "%H:%M").time()
                h_cierra = datetime.strptime(cierra, "%H:%M").time()
            except ValueError:
                messages.error(request, f"Hora inválida en {nombre}.")
                return redirect("horarios_oferente")
            if activo and h_cierra <= h_abre:
                messages.error(request, f"{nombre}: la hora de cierre debe ser después de la de inicio.")
                return redirect("horarios_oferente")
            Horario.objects.update_or_create(
                oferente=oferente, dia=dia,
                defaults={"abre": h_abre, "cierra": h_cierra, "activo": activo},
            )
        messages.success(request, "Agenda actualizada. Los clientes ven esos huecos libres.")
        return redirect("horarios_oferente")
    return render(request, "servicios/horarios.html", {
        "oferente": oferente,
        "filas": filas,
        "espacios": espacios_panel(oferente),
    })


@login_required(login_url="entrar_cuenta")
def fotos(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    actuales = list(oferente.fotos.all())
    if request.method == "POST":
        if request.POST.get("borrar"):
            foto = get_object_or_404(FotoTrabajo, pk=request.POST.get("borrar"), oferente=oferente)
            borrar_foto(foto.ruta)
            foto.delete()
            messages.success(request, "Foto quitada.")
            return redirect("fotos_oferente")
        archivos = request.FILES.getlist("fotos")
        if len(actuales) + len(archivos) > 10:
            messages.error(request, "Puedes tener hasta 10 fotos de tus trabajos.")
            return redirect("fotos_oferente")
        try:
            preparados = [extension(archivo) for archivo in archivos]
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("fotos_oferente")
        orden = (actuales[-1].orden + 1) if actuales else 1
        for archivo, (ext, tipo) in zip(archivos, preparados):
            ruta = f"servicios/{oferente.id}/{orden}-{uuid.uuid4().hex[:10]}.{ext}"
            url = subir_foto(archivo.read(), ruta, tipo)
            FotoTrabajo.objects.create(oferente=oferente, url=url, ruta=ruta, orden=orden)
            if not oferente.foto_url:
                oferente.foto_url = url
                oferente.foto_ruta = ruta
                oferente.save(update_fields=["foto_url", "foto_ruta"])
            orden += 1
        messages.success(request, "Fotos guardadas.")
        return redirect("fotos_oferente")
    return render(request, "servicios/fotos.html", {"oferente": oferente, "fotos": actuales})


@login_required(login_url="entrar_cuenta")
def activar(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    if oferente.inscripcion_pagada:
        if not oferente.mensualidad_al_dia:
            return redirect("mensualidad_oferente")
        messages.success(request, "La inscripción ya está paga.")
        return redirect("panel_oferente")
    cobro = abrir_cobro_inscripcion(oferente)
    if cobro.estado_pago == "aprobado":
        return redirect("mensualidad_oferente")
    if cobro.estado_pago in ("declinado", "error") or not cobro.referencia_pago:
        cobro.monto_cop = cuota_primera()
        cobro.referencia_pago = nueva_referencia("ACT", oferente.id)
        cobro.estado_pago = "pendiente"
        cobro.save()
    ctx = {
        "oferente": oferente,
        "cobro": cobro,
        "tarjeta_lista": wompi.checkout_listo(),
        "cuota": cuota_primera(),
        "mensualidad": cuota_mensualidad(),
        "inscripcion": cuota_activacion(),
    }
    if ctx["tarjeta_lista"]:
        destino = request.build_absolute_uri(reverse("resultado_activacion"))
        ctx["wompi"] = wompi.contexto_widget(cobro, destino)
    return render(request, "servicios/activar.html", ctx)


@login_required(login_url="entrar_cuenta")
def resultado_activacion(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    cobro = getattr(oferente, "activacion", None)
    tx_id = (request.GET.get("id") or "").strip()[:80]
    if cobro and tx_id:
        publica = wompi.claves_wompi()[0]
        tx = wompi.consultar_transaccion(tx_id, publica)
        if tx and (tx.get("reference") or "") == cobro.referencia_pago:
            if int(tx.get("amount_in_cents") or 0) == wompi.monto_centavos(cobro):
                aplicar_transaccion(tx)
                cobro.refresh_from_db()
                oferente.refresh_from_db()
    inscrito = cobro and cobro.estado_pago == "aprobado"
    return render(request, "servicios/resultado_activacion.html", {
        "oferente": oferente,
        "cobro": cobro,
        "pagado": inscrito,
        "falta_mensualidad": inscrito and not oferente.mensualidad_al_dia,
        "mensualidad": cuota_mensualidad(),
    })


@login_required(login_url="entrar_cuenta")
def mensualidad(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    if not oferente.inscripcion_pagada:
        messages.info(request, "Primero paga la inscripción y el primer mes.")
        return redirect("activar_oferente")
    cobro = abrir_cobro_mensual(oferente)
    if cobro is None:
        cobro = PagoMensualidad.objects.create(
            oferente=oferente,
            monto_cop=cuota_mensualidad(),
            referencia_pago=nueva_referencia("MEN", oferente.id),
        )
    ctx = {
        "oferente": oferente,
        "cobro": cobro,
        "tarjeta_lista": wompi.checkout_listo(),
        "cuota": cuota_mensualidad(),
    }
    if ctx["tarjeta_lista"]:
        destino = request.build_absolute_uri(reverse("resultado_mensualidad"))
        ctx["wompi"] = wompi.contexto_widget(cobro, destino)
    return render(request, "servicios/mensualidad.html", ctx)


@login_required(login_url="entrar_cuenta")
def resultado_mensualidad(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    cobro = oferente.pagos_mensuales.order_by("-id").first()
    tx_id = (request.GET.get("id") or "").strip()[:80]
    if cobro and tx_id:
        publica = wompi.claves_wompi()[0]
        tx = wompi.consultar_transaccion(tx_id, publica)
        if tx and (tx.get("reference") or "") == cobro.referencia_pago:
            if int(tx.get("amount_in_cents") or 0) == wompi.monto_centavos(cobro):
                aplicar_transaccion(tx)
                cobro.refresh_from_db()
                oferente.refresh_from_db()
    return render(request, "servicios/resultado_mensualidad.html", {
        "oferente": oferente,
        "cobro": cobro,
        "pagado": oferente.visible,
        "mensualidad": cuota_mensualidad(),
    })


def contratar(request, slug):
    oferente = get_object_or_404(_publico(), slug=slug)
    if not request.user.is_authenticated:
        return redirect(f"/entrar/?next={request.get_full_path()}")
    if oferente.user_id == request.user.id:
        messages.error(request, "No puedes contratarte a ti mismo.")
        return redirect("detalle_oferente", slug=slug)
    if not oferente.disponible_ahora:
        messages.error(request, "Este oferente no está recibiendo citas ahora.")
        return redirect("detalle_oferente", slug=slug)
    especialidades = oferente.especialidades.filter(activa=True)
    coberturas = oferente.coberturas.filter(activa=True)
    esp = especialidades.filter(pk=request.GET.get("oficio") or request.POST.get("especialidad") or 0).first()
    if esp is None:
        esp = especialidades.first()
    cob = coberturas.filter(pk=request.POST.get("cobertura") or request.GET.get("zona") or 0).first()
    if cob is None:
        cob = coberturas.first()
    cantidad = int(request.GET.get("cantidad") or request.POST.get("cantidad") or 1)
    cantidad = max(min(cantidad, 12), 1)
    inicio_raw = request.GET.get("inicio") or request.POST.get("inicio") or ""
    inicio = parse_datetime(inicio_raw)
    if inicio is None:
        messages.error(request, "Elige un espacio libre de la agenda.")
        return redirect("detalle_oferente", slug=slug)
    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
    if esp and esp.modo_tiempo != "cita":
        fin = inicio + duracion_largo(esp, cantidad)
        monto = (esp.precio_cop if esp else oferente.precio_cop) * cantidad
    else:
        fin = inicio + duracion_cita(esp, oferente)
        monto = esp.precio_cop if esp else oferente.precio_cop
        cantidad = 1
    if not hueco_libre(oferente, inicio, fin, esp):
        messages.error(request, "Ese espacio ya no está libre. Elige otro.")
        return redirect("detalle_oferente", slug=slug)
    inicial = {"inicio": inicio.isoformat()}
    inicial["nombre"] = request.user.get_full_name() or request.user.username
    inicial["email"] = request.user.email or ""
    try:
        inicial["nombre"] = request.user.comprador.nombre
        inicial["telefono"] = request.user.comprador.telefono
        inicial["email"] = request.user.email or inicial["email"]
    except ObjectDoesNotExist:
        try:
            tienda = request.user.vendedor
            inicial["nombre"] = tienda.responsable
            inicial["telefono"] = tienda.telefono
        except ObjectDoesNotExist:
            ofe = _oferente(request.user)
            if ofe:
                inicial["nombre"] = ofe.responsable
                inicial["telefono"] = ofe.telefono
    form = ContratarForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        inicio = data["inicio"]
        if timezone.is_naive(inicio):
            inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
        if esp and esp.modo_tiempo != "cita":
            fin = inicio + duracion_largo(esp, cantidad)
            monto = (esp.precio_cop if esp else oferente.precio_cop) * cantidad
        else:
            fin = inicio + duracion_cita(esp, oferente)
            monto = esp.precio_cop if esp else oferente.precio_cop
        if not hueco_libre(oferente, inicio, fin, esp):
            messages.error(request, "Ese espacio ya no está libre. Elige otro.")
            return redirect("detalle_oferente", slug=slug)
        with transaction.atomic():
            cita = Cita(
                oferente=oferente,
                especialidad=esp,
                cobertura=cob,
                cliente=request.user if request.user.is_authenticated else None,
                inicio=inicio,
                fin=fin,
                modo_tiempo=esp.modo_tiempo if esp else "cita",
                cliente_nombre=data["nombre"],
                cliente_telefono=data["telefono"],
                cliente_email=data.get("email") or "",
                nota=data.get("nota") or "",
                monto_cop=monto,
                clave_contacto=uuid.uuid4().hex,
                estado="pendiente",
                estado_pago="pendiente",
            )
            aplicar_comision_cita(cita)
            cita.save()
            cita.referencia_pago = nueva_referencia("SRV", cita.id)
            cita.save(update_fields=["referencia_pago"])
        avisar_agenda(request, cita)
        return redirect(f"{reverse('pagar_cita', args=[cita.id])}?clave={cita.clave_contacto}")
    return render(request, "servicios/contratar.html", {
        "oferente": oferente,
        "form": form,
        "inicio": inicio,
        "fin": fin,
        "especialidad": esp,
        "cobertura": cob,
        "coberturas": coberturas,
        "cantidad": cantidad,
    })


def _cita_clave(request, cita_id):
    cita = get_object_or_404(Cita.objects.select_related("oferente", "especialidad", "comentario"), pk=cita_id)
    clave = (request.GET.get("clave") or request.POST.get("clave") or "").strip()
    dueno = request.user.is_authenticated and (
        cita.cliente_id == request.user.id or _oferente(request.user) == cita.oferente or request.user.is_staff
    )
    if clave != cita.clave_contacto and not dueno:
        return None, None
    return cita, clave


def pagar_cita(request, cita_id):
    cita, clave = _cita_clave(request, cita_id)
    if cita is None:
        messages.error(request, "No se encontró esa cita.")
        return redirect("lista_servicios")
    if cita.estado_pago == "aprobado":
        return redirect(f"{reverse('resultado_cita', args=[cita.id])}?clave={cita.clave_contacto}")
    ctx = {
        "cita": cita,
        "clave": clave or cita.clave_contacto,
        "tarjeta_lista": wompi.checkout_listo(),
        "contacto_visible": False,
    }
    if ctx["tarjeta_lista"]:
        destino = request.build_absolute_uri(
            reverse("resultado_cita", args=[cita.id]) + f"?clave={cita.clave_contacto}"
        )
        ctx["wompi"] = wompi.contexto_widget(cita, destino)
    return render(request, "servicios/pagar.html", ctx)


def resultado_cita(request, cita_id):
    cita, clave = _cita_clave(request, cita_id)
    if cita is None:
        messages.error(request, "No se encontró esa cita.")
        return redirect("lista_servicios")
    tx_id = (request.GET.get("id") or "").strip()[:80]
    if tx_id:
        publica = wompi.claves_wompi()[0]
        tx = wompi.consultar_transaccion(tx_id, publica)
        if tx and (tx.get("reference") or "") == cita.referencia_pago:
            if int(tx.get("amount_in_cents") or 0) == wompi.monto_centavos(cita):
                aplicar_transaccion(tx)
                cita.refresh_from_db()
    contacto = cita.estado_pago == "aprobado"
    form = None
    try:
        ya_comento = cita.comentario is not None
    except ObjectDoesNotExist:
        ya_comento = False
    es_oferente = request.user.is_authenticated and _oferente(request.user) == cita.oferente
    es_cliente = (not request.user.is_authenticated) or cita.cliente_id == request.user.id or clave == cita.clave_contacto
    if contacto and request.method == "POST" and es_cliente and not es_oferente:
        quiere_cerrar = bool(request.POST.get("realizar") or request.POST.get("cerrar"))
        quiere_comentar = bool(request.POST.get("comentar") or request.POST.get("cerrar"))
        if quiere_comentar and not ya_comento:
            form = ComentarioForm(request.POST)
            if form.is_valid():
                Comentario.objects.create(
                    cita=cita,
                    oferente=cita.oferente,
                    estrellas=int(form.cleaned_data["estrellas"]),
                    texto=form.cleaned_data.get("texto") or "",
                    nombre=cita.cliente_nombre,
                )
                ya_comento = True
            elif quiere_cerrar:
                messages.error(request, "Califica el servicio para que ERA shop gire el pago al Nequi del oferente.")
                return render(request, "servicios/resultado.html", {
                    "cita": cita,
                    "pagado": contacto,
                    "contacto_visible": contacto,
                    "form": form,
                    "clave": cita.clave_contacto,
                    "puede_cerrar": not cita.trabajo_realizado,
                    "ya_comento": False,
                })
        if quiere_cerrar and not cita.trabajo_realizado:
            if not ya_comento:
                messages.error(request, "Primero califica el trabajo. El giro sale cuando hay calificación y visto bueno.")
            else:
                cita.trabajo_realizado = True
                cita.realizado_en = timezone.now()
                cita.save(update_fields=["trabajo_realizado", "realizado_en"])
        if ya_comento and cita.trabajo_realizado:
            giro = intentar_giro_servicio(cita)
            if giro:
                messages.success(request, "Quedó realizado y calificado. El dinero sigue en Wompi hasta que ERA shop autorice el giro.")
            else:
                messages.success(request, "Gracias. El trabajo y la calificación quedaron registrados.")
            return redirect(f"{reverse('resultado_cita', args=[cita.id])}?clave={cita.clave_contacto}")
        if ya_comento and not quiere_cerrar:
            messages.success(request, "Gracias por la calificación. Cuando marques el trabajo como realizado, sale el giro.")
            return redirect(f"{reverse('resultado_cita', args=[cita.id])}?clave={cita.clave_contacto}")
    if contacto and not ya_comento:
        form = form or ComentarioForm()
    return render(request, "servicios/resultado.html", {
        "cita": cita,
        "pagado": contacto,
        "contacto_visible": contacto,
        "form": form,
        "clave": cita.clave_contacto,
        "puede_cerrar": contacto and not cita.trabajo_realizado and not es_oferente,
        "ya_comento": ya_comento,
    })


@login_required(login_url="entrar_cuenta")
def toggle_espacio(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    if request.method != "POST":
        return redirect("horarios_oferente")
    inicio = parse_datetime(request.POST.get("inicio") or "")
    fin = parse_datetime(request.POST.get("fin") or "")
    if inicio is None or fin is None:
        messages.error(request, "Ese espacio no se pudo leer.")
        return redirect("horarios_oferente")
    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
    if timezone.is_naive(fin):
        fin = timezone.make_aware(fin, timezone.get_current_timezone())
    existente = Bloqueo.objects.filter(oferente=oferente, inicio=inicio, fin=fin).first()
    if existente:
        existente.delete()
        messages.success(request, "Espacio marcado otra vez como libre.")
    else:
        from .agenda import citas_que_ocupan
        if citas_que_ocupan(oferente, inicio, fin).exists():
            messages.error(request, "Ese espacio ya tiene una cita pagada o reservada.")
            return redirect("horarios_oferente")
        Bloqueo.objects.create(oferente=oferente, inicio=inicio, fin=fin)
        messages.success(request, "Espacio bloqueado. El cliente ya no lo ve libre.")
    return redirect("horarios_oferente")


@login_required(login_url="entrar_cuenta")
def ampliar(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return redirect("registro_oferente")
    if oferente.estado != "activo":
        messages.error(request, "Primero paga la cuota para aparecer.")
        return redirect("activar_oferente")
    if request.method == "POST":
        tipo = request.POST.get("tipo")
        if tipo == "ciudad":
            departamento = (request.POST.get("departamento") or "").strip()
            municipio = (request.POST.get("municipio") or request.POST.get("ciudad") or "").strip()
            if not departamento or not municipio:
                messages.error(request, "Elige departamento y municipio.")
                return redirect("ampliar_oferente")
            cob, creado = Cobertura.objects.get_or_create(
                oferente=oferente, departamento=departamento, municipio=municipio,
                defaults={"incluida": False, "activa": False},
            )
            if cob.activa:
                messages.success(request, "Esa ciudad ya está activa.")
                return redirect("panel_oferente")
            extra = PagoExtra.objects.create(
                oferente=oferente, tipo="ciudad", cobertura=cob,
                monto_cop=cuota_activacion(),
                referencia_pago=nueva_referencia("EXT", cob.id),
            )
            return redirect("pagar_extra", extra.id)
        if tipo == "servicio":
            rubro = (request.POST.get("rubro") or "").strip()
            oficio = (request.POST.get("oficio") or "").strip()
            try:
                precio = int(request.POST.get("precio_cop") or 0)
            except ValueError:
                precio = 0
            modo = (request.POST.get("modo_tiempo") or "cita").strip()
            if modo not in dict(MODOS_TIEMPO):
                modo = "cita"
            cobro = (request.POST.get("modo_cobro") or "ambos").strip()
            tarifa_detalle = (request.POST.get("tarifa_detalle") or "").strip()
            if cobro not in ("tarifa", "negociar", "ambos"):
                cobro = "ambos"
            if not rubro or not oficio:
                messages.error(request, "Elige el oficio.")
                return redirect("ampliar_oferente")
            if cobro != "negociar" and precio < 1000:
                messages.error(request, "Publica una tarifa o marca que se cotiza.")
                return redirect("ampliar_oferente")
            if oferente.especialidades.filter(rubro=rubro, oficio=oficio, activa=True).exists():
                messages.error(request, "Ese oficio ya lo tienes activo.")
                return redirect("ampliar_oferente")
            esp, _c = Especialidad.objects.get_or_create(
                oferente=oferente, rubro=rubro, oficio=oficio,
                defaults={
                    "precio_cop": precio,
                    "unidad": "dia" if modo == "dia" else ("semana" if modo == "semana" else "visita"),
                    "modo_tiempo": modo,
                    "duracion_minutos": int(request.POST.get("duracion_minutos") or 60),
                    "modo_cobro": cobro,
                    "tarifa_detalle": tarifa_detalle,
                    "incluida": False,
                    "activa": False,
                },
            )
            if not _c:
                esp.precio_cop = precio
                esp.modo_tiempo = modo
                esp.modo_cobro = cobro
                esp.tarifa_detalle = tarifa_detalle
                esp.save()
            extra = PagoExtra.objects.create(
                oferente=oferente, tipo="servicio", especialidad=esp,
                monto_cop=cuota_activacion(),
                referencia_pago=nueva_referencia("EXT", esp.id),
            )
            return redirect("pagar_extra", extra.id)
    return render(request, "servicios/ampliar.html", {
        "oferente": oferente,
        "cuota": cuota_activacion(),
        "rubros": rubros_choices(),
        "oficios_json": json.dumps(oficios_mapa()),
        "municipios_json": json.dumps(MUNICIPIOS),
        "departamentos": DEPARTAMENTOS,
        "modos": MODOS_TIEMPO,
        "coberturas": oferente.coberturas.all(),
        "especialidades": oferente.especialidades.all(),
    })


@login_required(login_url="entrar_cuenta")
def pagar_extra(request, extra_id):
    oferente = _oferente(request.user)
    extra = get_object_or_404(PagoExtra, pk=extra_id, oferente=oferente)
    if extra.estado_pago == "aprobado":
        messages.success(request, "Ese pago ya quedó.")
        return redirect("panel_oferente")
    if extra.estado_pago in ("declinado", "error"):
        extra.referencia_pago = nueva_referencia("EXT", extra.id)
        extra.estado_pago = "pendiente"
        extra.save()
    ctx = {
        "oferente": oferente,
        "cobro": extra,
        "tarjeta_lista": wompi.checkout_listo(),
        "cuota": cuota_activacion(),
        "extra": extra,
    }
    if ctx["tarjeta_lista"]:
        destino = request.build_absolute_uri(reverse("resultado_extra", args=[extra.id]))
        ctx["wompi"] = wompi.contexto_widget(extra, destino)
    return render(request, "servicios/pagar_extra.html", ctx)


@login_required(login_url="entrar_cuenta")
def resultado_extra(request, extra_id):
    oferente = _oferente(request.user)
    extra = get_object_or_404(PagoExtra, pk=extra_id, oferente=oferente)
    tx_id = (request.GET.get("id") or "").strip()[:80]
    if tx_id:
        publica = wompi.claves_wompi()[0]
        tx = wompi.consultar_transaccion(tx_id, publica)
        if tx and (tx.get("reference") or "") == extra.referencia_pago:
            if int(tx.get("amount_in_cents") or 0) == wompi.monto_centavos(extra):
                aplicar_transaccion(tx)
                extra.refresh_from_db()
    return render(request, "servicios/resultado_extra.html", {
        "extra": extra,
        "pagado": extra.estado_pago == "aprobado",
        "oferente": oferente,
    })


def preguntar_precio(request, slug):
    oferente = get_object_or_404(_publico(), slug=slug)
    especialidades = oferente.especialidades.filter(activa=True)
    esp = especialidades.filter(pk=request.POST.get("especialidad") or request.GET.get("oficio") or 0).first()
    if request.method != "POST":
        return redirect("detalle_oferente", slug=slug)
    nombre = (request.POST.get("nombre") or "").strip()
    telefono = (request.POST.get("telefono") or "").strip()
    email = (request.POST.get("email") or "").strip()
    texto = sin_contacto(request.POST.get("mensaje") or "")
    if len(nombre) < 3 or len(telefono) < 7 or len(texto) < 8:
        messages.error(request, "Escribe tu nombre, un teléfono y qué necesitas. El oferente no verá el teléfono hasta que pagues.")
        return redirect("detalle_oferente", slug=slug)
    consulta = Consulta.objects.create(
        oferente=oferente,
        especialidad=esp,
        cliente=request.user if request.user.is_authenticated else None,
        cliente_nombre=nombre,
        cliente_telefono=telefono,
        cliente_email=email,
        clave=uuid.uuid4().hex,
    )
    MensajeConsulta.objects.create(consulta=consulta, autor="cliente", texto=texto)
    avisar_consulta(request, consulta)
    messages.success(request, "La pregunta quedó. El oferente recibe un aviso en el celular. Hablen aquí, sin WhatsApp.")
    return redirect(f"{reverse('consulta_servicio', args=[consulta.id])}?clave={consulta.clave}")


def consulta_servicio(request, consulta_id):
    consulta = get_object_or_404(
        Consulta.objects.select_related("oferente", "especialidad", "cita"), pk=consulta_id,
    )
    clave = (request.GET.get("clave") or request.POST.get("clave") or "").strip()
    es_oferente = request.user.is_authenticated and _oferente(request.user) == consulta.oferente
    es_cliente = clave == consulta.clave or (
        request.user.is_authenticated and consulta.cliente_id == request.user.id
    )
    if not es_oferente and not es_cliente and not request.user.is_staff:
        messages.error(request, "Esa cotización no está disponible.")
        return redirect("lista_servicios")
    if es_oferente:
        consulta.visto_oferente = timezone.now()
        consulta.save(update_fields=["visto_oferente"])
    if request.method == "POST":
        if request.POST.get("propuesta") and es_oferente:
            try:
                valor = int(request.POST.get("propuesta_cop") or 0)
            except ValueError:
                valor = 0
            if valor >= 1000:
                consulta.propuesta_cop = valor
                consulta.save(update_fields=["propuesta_cop"])
                MensajeConsulta.objects.create(
                    consulta=consulta,
                    autor="oferente",
                    texto=sin_contacto(f"Tarifa propuesta: ${valor} COP. Si te sirve, págala en la página."),
                )
                messages.success(request, "Quedó la tarifa. El cliente puede pagarla aquí.")
        elif request.POST.get("pagar") and es_cliente and consulta.propuesta_cop:
            with transaction.atomic():
                cita = Cita(
                    oferente=consulta.oferente,
                    especialidad=consulta.especialidad,
                    cliente=consulta.cliente,
                    inicio=timezone.now(),
                    fin=timezone.now(),
                    modo_tiempo="cita",
                    cliente_nombre=consulta.cliente_nombre,
                    cliente_telefono=consulta.cliente_telefono,
                    cliente_email=consulta.cliente_email,
                    nota="Cotización aceptada",
                    monto_cop=consulta.propuesta_cop,
                    clave_contacto=consulta.clave,
                    estado="pendiente",
                    estado_pago="pendiente",
                )
                aplicar_comision_cita(cita)
                cita.save()
                cita.referencia_pago = nueva_referencia("SRV", cita.id)
                cita.save(update_fields=["referencia_pago"])
                consulta.cita = cita
                consulta.estado = "aceptada"
                consulta.save(update_fields=["cita", "estado"])
            avisar_agenda(request, cita)
            return redirect(f"{reverse('pagar_cita', args=[cita.id])}?clave={cita.clave_contacto}")
        else:
            texto = sin_contacto(request.POST.get("texto") or "")
            if texto:
                autor = "oferente" if es_oferente else "cliente"
                MensajeConsulta.objects.create(consulta=consulta, autor=autor, texto=texto)
                avisar_mensaje_consulta(request, consulta, autor)
        return redirect(f"{reverse('consulta_servicio', args=[consulta.id])}?clave={consulta.clave}")
    return render(request, "servicios/consulta.html", {
        "consulta": consulta,
        "mensajes": consulta.mensajes.all(),
        "es_oferente": es_oferente,
        "es_cliente": es_cliente,
        "clave": consulta.clave,
        "contacto_visible": bool(consulta.cita_id and consulta.cita.estado_pago == "aprobado"),
    })


@require_GET
def alertas_oferente(request):
    oferente = _oferente(request.user)
    if oferente is None:
        return JsonResponse({"n": 0, "items": []})
    from pedidos.models import Aviso
    avisos = list(Aviso.objects.filter(user=request.user, leido=False).order_by("-id")[:8])
    return JsonResponse({
        "n": Aviso.objects.filter(user=request.user, leido=False).count(),
        "items": [{"t": a.titulo, "x": a.texto[:160], "u": a.url} for a in avisos],
    })
