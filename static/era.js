function absoluto(ruta) {
  return new URL(ruta, window.location.origin).href;
}

function textoCompartir(nodo) {
  const titulo = nodo.dataset.title || "ERA shop";
  const texto = nodo.dataset.text || titulo;
  const url = absoluto(nodo.dataset.url || "/");
  return { titulo, texto, url, precio: nodo.dataset.price || "", kicker: nodo.dataset.kicker || "ERA shop" };
}

function envolver(ctx, texto, x, y, max, linea) {
  const palabras = texto.split(" ");
  let fila = "";
  palabras.forEach(function (palabra) {
    const prueba = fila ? fila + " " + palabra : palabra;
    if (ctx.measureText(prueba).width > max && fila) {
      ctx.fillText(fila, x, y);
      y += linea;
      fila = palabra;
    } else {
      fila = prueba;
    }
  });
  if (fila) ctx.fillText(fila, x, y);
  return y;
}

async function imagenEstado(datos) {
  const lienzo = document.createElement("canvas");
  lienzo.width = 1080;
  lienzo.height = 1920;
  const ctx = lienzo.getContext("2d");
  ctx.fillStyle = "#14110e";
  ctx.fillRect(0, 0, 1080, 1920);
  const fondo = ctx.createRadialGradient(860, 120, 40, 860, 180, 620);
  fondo.addColorStop(0, "#e23b22");
  fondo.addColorStop(1, "rgba(226,59,34,0)");
  ctx.fillStyle = fondo;
  ctx.fillRect(0, 0, 1080, 1920);
  ctx.fillStyle = "#f6f1e8";
  ctx.font = "700 42px Outfit, sans-serif";
  ctx.fillText("ERA SHOP", 80, 180);
  ctx.fillStyle = "#ffb2a4";
  ctx.font = "600 36px Outfit, sans-serif";
  ctx.fillText(datos.kicker.slice(0, 42), 80, 260);
  ctx.fillStyle = "#fffaf3";
  ctx.font = "500 92px Outfit, sans-serif";
  const y = envolver(ctx, datos.titulo, 80, 620, 900, 104);
  if (datos.precio) {
    ctx.font = "750 72px Outfit, sans-serif";
    ctx.fillStyle = "#ffe08a";
    ctx.fillText(datos.precio, 80, y + 120);
  }
  ctx.fillStyle = "#f6f1e8";
  ctx.font = "500 40px Outfit, sans-serif";
  ctx.fillText("Toca el enlace y haz el pedido", 80, 1680);
  ctx.font = "500 32px Outfit, sans-serif";
  ctx.fillStyle = "#ffd0c6";
  ctx.fillText(datos.url.replace(/^https?:\/\//, "").slice(0, 48), 80, 1760);
  const blob = await new Promise(function (resolver) { lienzo.toBlob(resolver, "image/png"); });
  return new File([blob], "era-shop.png", { type: "image/png" });
}

async function publicarEstado(nodo) {
  const datos = textoCompartir(nodo);
  const archivo = await imagenEstado(datos);
  const mensaje = datos.texto + " " + datos.url;
  if (navigator.share) {
    const carga = { title: datos.titulo, text: mensaje, url: datos.url };
    if (navigator.canShare && navigator.canShare({ files: [archivo] })) carga.files = [archivo];
    await navigator.share(carga);
    return;
  }
  await navigator.clipboard.writeText(mensaje);
  const enlace = document.createElement("a");
  enlace.href = URL.createObjectURL(archivo);
  enlace.download = "era-shop-estado.png";
  enlace.click();
  alert("Se copió el enlace y se descargó la imagen del estado. Súbela a WhatsApp, Instagram o Facebook.");
}

function prepararCompartir(nodo) {
  const datos = textoCompartir(nodo);
  const mensaje = encodeURIComponent(datos.texto + " " + datos.url);
  const wa = nodo.querySelector("[data-net='whatsapp']");
  const fb = nodo.querySelector("[data-net='facebook']");
  if (wa) wa.href = "https://wa.me/?text=" + mensaje;
  if (fb) fb.href = "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(datos.url);
  nodo.querySelectorAll("[data-kind='estado']").forEach(function (boton) {
    boton.addEventListener("click", function () {
      publicarEstado(nodo).catch(function () {
        window.prompt("Copia este enlace para tu estado:", datos.url);
      });
    });
  });
  nodo.querySelectorAll("[data-kind='copiar']").forEach(function (boton) {
    boton.addEventListener("click", function () {
      navigator.clipboard.writeText(datos.url).then(function () {
        boton.textContent = "Enlace copiado";
      });
    });
  });
}

function abrirNequi(numero) {
  navigator.clipboard.writeText(numero).catch(function () {});
  const movil = /Android|iPhone|iPad/i.test(navigator.userAgent || "");
  if (movil) window.location.href = "nequi://home";
}

function prepararSlider(slider) {
  const pista = slider.querySelector(".slider-track");
  if (!pista) return;
  const fotos = pista.querySelectorAll("img");
  const puntos = slider.querySelectorAll(".dot");
  function indice() {
    const ancho = pista.clientWidth || 1;
    return Math.round(pista.scrollLeft / ancho);
  }
  function marcar() {
    const actual = indice();
    puntos.forEach(function (punto, i) {
      punto.classList.toggle("on", i === actual);
    });
  }
  function ir(i) {
    const destino = Math.max(0, Math.min(fotos.length - 1, i));
    pista.scrollTo({ left: destino * pista.clientWidth, behavior: "smooth" });
  }
  slider.querySelectorAll(".slider-nav").forEach(function (boton) {
    boton.addEventListener("click", function () {
      ir(indice() + Number(boton.dataset.dir || 1));
    });
  });
  puntos.forEach(function (punto) {
    punto.addEventListener("click", function () { ir(Number(punto.dataset.i)); });
  });
  pista.addEventListener("scroll", marcar, { passive: true });
  slider.addEventListener("keydown", function (evento) {
    if (evento.key === "ArrowRight") ir(indice() + 1);
    if (evento.key === "ArrowLeft") ir(indice() - 1);
  });
}

function prepararRiel(riel) {
  let activo = false;
  let inicio = 0;
  let izquierda = 0;
  riel.addEventListener("pointerdown", function (evento) {
    if (evento.target.closest("a, button, input, select, textarea")) return;
    activo = true;
    inicio = evento.clientX;
    izquierda = riel.scrollLeft;
    riel.setPointerCapture(evento.pointerId);
  });
  riel.addEventListener("pointermove", function (evento) {
    if (!activo) return;
    riel.scrollLeft = izquierda - (evento.clientX - inicio);
  });
  function soltar() { activo = false; }
  riel.addEventListener("pointerup", soltar);
  riel.addEventListener("pointercancel", soltar);
}

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-slider]").forEach(prepararSlider);
  document.querySelectorAll("[data-rail]").forEach(prepararRiel);
  document.querySelectorAll("[data-share]").forEach(prepararCompartir);
  document.querySelectorAll("[data-abrir-nequi]").forEach(function (boton) {
    boton.addEventListener("click", function () { abrirNequi(boton.dataset.abrirNequi); });
  });
});
