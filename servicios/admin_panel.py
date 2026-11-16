import json
from datetime import time

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from vendedores.opciones import DEPARTAMENTOS

from .catalogo import oficios_mapa, rubros_choices, sembrar_catalogo
from .forms import RegistroOferenteForm
from .models import (
    Cita,
    Cobertura,
    Especialidad,
    GiroCita,
    Horario,
    Oferente,
    OficioCatalogo,
    RubroCatalogo,
)
from .municipios import MUNICIPIOS
from .oficios import MODOS_TIEMPO, UNIDADES
from .pagos import cuota_activacion


def _staff(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path(), login_url="/admin/login/")
    return None


def panel(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    sembrar_catalogo()
    giros = GiroCita.objects.select_related("cita__oferente").exclude(estado="pagado")
    return render(request, "servicios/admin_home.html", {
        "oferentes": Oferente.objects.select_related("user")[:80],
        "rubros": RubroCatalogo.objects.prefetch_related("oficios"),
        "pendientes": giros,
        "cuota": cuota_activacion(),
    })


def consignaciones(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    hechos = (
        Cita.objects.filter(trabajo_realizado=True, estado_pago="aprobado")
        .select_related("oferente", "especialidad")
        .order_by("-realizado_en", "-id")
    )
    filas = []
    for cita in hechos:
        try:
            giro = cita.giro
        except GiroCita.DoesNotExist:
            giro = None
        filas.append({
            "cita": cita,
            "giro": giro,
            "nequi": (giro.destino_nequi if giro and giro.destino_nequi else cita.oferente.nequi) or "Sin Nequi",
            "monto": (giro.monto_cop if giro else cita.neto_vendedor) or 0,
            "estado": giro.estado if giro else "pendiente",
            "consignado": giro.estado == "pagado" if giro else False,
        })
    return render(request, "servicios/admin_giros.html", {"filas": filas})


@require_POST
def marcar_consignado(request, cita_id):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    cita = get_object_or_404(Cita.objects.select_related("oferente"), pk=cita_id)
    giro, _ = GiroCita.objects.get_or_create(
        cita=cita,
        defaults={
            "monto_cop": cita.neto_vendedor or 0,
            "comision_cop": cita.comision_cop or 0,
            "destino_nequi": (cita.oferente.nequi or "")[:20],
        },
    )
    giro.monto_cop = cita.neto_vendedor or 0
    giro.comision_cop = cita.comision_cop or 0
    giro.destino_nequi = (cita.oferente.nequi or "")[:20]
    giro.estado = "pagado"
    giro.detalle = (request.POST.get("comprobante") or "Consignado a mano por el administrador.")[:300]
    giro.save()
    cita.estado_comision = "pagada"
    cita.save(update_fields=["estado_comision"])
    messages.success(request, f"Quedó consignado ${giro.monto_cop} al Nequi {giro.destino_nequi}.")
    return redirect("admin_consignaciones")


def catalogo(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    sembrar_catalogo()
    if request.method == "POST":
        tipo = request.POST.get("tipo")
        if tipo == "rubro":
            clave = slugify(request.POST.get("clave") or request.POST.get("nombre") or "")[:40]
            nombre = (request.POST.get("nombre") or "").strip()
            if clave and nombre:
                RubroCatalogo.objects.update_or_create(
                    clave=clave, defaults={"nombre": nombre, "activo": True},
                )
                messages.success(request, "Tipo de servicio guardado.")
        elif tipo == "oficio":
            rubro = get_object_or_404(RubroCatalogo, pk=request.POST.get("rubro_id"))
            nombre = (request.POST.get("nombre") or "").strip()
            clave = slugify(request.POST.get("clave") or nombre)[:40]
            if nombre and clave:
                OficioCatalogo.objects.update_or_create(
                    rubro=rubro, clave=clave, defaults={"nombre": nombre, "activo": True},
                )
                messages.success(request, "Oficio guardado. Ya sale para inscribirse y buscar.")
        return redirect("admin_catalogo_servicios")
    return render(request, "servicios/admin_catalogo.html", {
        "rubros": RubroCatalogo.objects.prefetch_related("oficios"),
    })


@require_POST
def editar_oficio(request, pk):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    oficio = get_object_or_404(OficioCatalogo, pk=pk)
    nombre = (request.POST.get("nombre") or "").strip()
    if nombre:
        oficio.nombre = nombre
        oficio.activo = request.POST.get("activo") == "1"
        oficio.save()
        messages.success(request, "Oficio actualizado.")
    return redirect("admin_catalogo_servicios")


@require_POST
def borrar_oficio(request, pk):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    oficio = get_object_or_404(OficioCatalogo, pk=pk)
    oficio.delete()
    messages.success(request, "Oficio borrado del catálogo.")
    return redirect("admin_catalogo_servicios")


@require_POST
def editar_rubro(request, pk):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    rubro = get_object_or_404(RubroCatalogo, pk=pk)
    nombre = (request.POST.get("nombre") or "").strip()
    if nombre:
        rubro.nombre = nombre
        rubro.activo = request.POST.get("activo") == "1"
        rubro.save()
        messages.success(request, "Tipo actualizado.")
    return redirect("admin_catalogo_servicios")


@require_POST
def borrar_rubro(request, pk):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    rubro = get_object_or_404(RubroCatalogo, pk=pk)
    rubro.delete()
    messages.success(request, "Tipo de servicio borrado.")
    return redirect("admin_catalogo_servicios")


def oferentes(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    q = (request.GET.get("q") or "").strip()
    qs = Oferente.objects.select_related("user").all()
    if q:
        qs = qs.filter(nombre__icontains=q)
    return render(request, "servicios/admin_oferentes.html", {"oferentes": qs[:200], "q": q})


def oferente_nuevo(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    form = RegistroOferenteForm(request.POST or None, usuario=None)
    form.fields["acepta_terminos"].required = False
    if request.method == "POST":
        if not request.POST.get("acepta_terminos"):
            form.data = form.data.copy()
            form.data["acepta_terminos"] = "on"
            form = RegistroOferenteForm(form.data, usuario=None)
            form.fields["acepta_terminos"].required = False
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data["email"], email=data["email"], password=data["password"] or User.objects.make_random_password(),
                )
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
                    estado="activo",
                )
                for dia in range(6):
                    Horario.objects.create(oferente=oferente, dia=dia, abre=time(8, 0), cierra=time(18, 0), activo=True)
                Cobertura.objects.create(
                    oferente=oferente, departamento=oferente.departamento, municipio=oferente.ciudad,
                    incluida=True, activa=True,
                )
                Especialidad.objects.create(
                    oferente=oferente, rubro=oferente.rubro, oficio=oferente.oficio,
                    precio_cop=oferente.precio_cop, unidad=oferente.unidad,
                    modo_tiempo=data.get("modo_tiempo") or "cita",
                    duracion_minutos=oferente.duracion_minutos,
                    incluida=True, activa=True,
                )
            messages.success(request, "Oferente registrado y visible, sin cobrar la cuota.")
            return redirect("admin_oferentes")
    return render(request, "servicios/admin_oferente_form.html", {
        "form": form,
        "nuevo": True,
        "oficios_json": json.dumps(oficios_mapa()),
        "municipios_json": json.dumps(MUNICIPIOS),
    })


def oferente_editar(request, pk):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    oferente = get_object_or_404(Oferente, pk=pk)
    if request.method == "POST":
        for campo in (
            "nombre", "responsable", "documento", "telefono", "whatsapp", "nequi",
            "email", "ciudad", "departamento", "rubro", "oficio", "descripcion",
        ):
            valor = request.POST.get(campo)
            if valor is not None:
                setattr(oferente, campo, valor.strip() if isinstance(valor, str) else valor)
        if request.POST.get("precio_cop"):
            oferente.precio_cop = request.POST.get("precio_cop")
        if request.POST.get("estado") in dict(Oferente.ESTADOS):
            oferente.estado = request.POST.get("estado")
        oferente.disponible_ahora = request.POST.get("disponible_ahora") == "1"
        oferente.save()
        messages.success(request, "Oferente actualizado.")
        return redirect("admin_oferentes")
    return render(request, "servicios/admin_oferente_form.html", {
        "oferente": oferente,
        "nuevo": False,
        "estados": Oferente.ESTADOS,
        "departamentos": DEPARTAMENTOS,
        "rubros": rubros_choices(),
        "unidades": UNIDADES,
        "modos": MODOS_TIEMPO,
        "oficios_json": json.dumps(oficios_mapa()),
    })


@require_POST
def oferente_borrar(request, pk):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    oferente = get_object_or_404(Oferente, pk=pk)
    if oferente.citas.exists():
        oferente.estado = "suspendido"
        oferente.save(update_fields=["estado"])
        messages.success(request, "Tiene citas. Lo retiré de la página en vez de borrarlo.")
        return redirect("admin_oferentes")
    user = oferente.user
    oferente.delete()
    if user and not hasattr(user, "vendedor"):
        try:
            user.delete()
        except Exception:
            pass
    messages.success(request, "Oferente borrado.")
    return redirect("admin_oferentes")
