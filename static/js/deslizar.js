/*
 * Gesto de deslizar en celular: izquierda → siguiente sección, derecha → anterior.
 * El orden sale de los enlaces del encabezado (data-orden). Cada sección sigue siendo
 * una URL real: esto solo decide A DÓNDE ir; la animación la hace el navegador (View Transitions).
 *
 * No se activa si el dedo empieza en algo que ya se desliza solo (tablas, calendario,
 * gráficas, la barra de secciones) ni en los bordes de la pantalla, que el celular
 * usa para su propio gesto de "atrás".
 */
(function () {
  "use strict";
  var main = document.querySelector("main");
  var enlaces = Array.prototype.slice.call(document.querySelectorAll(".secciones a[data-orden]"));
  var actual = Number(document.documentElement.dataset.seccion);
  if (!main || enlaces.length < 2 || actual < 0) return;

  var reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var IGNORAR = ".tabla, .lienzo, .cal, .horas, .tipos, .secciones, .segmentos, input, textarea, select, button, label, dialog, [data-sin-deslizar]";
  var BORDE = 24, MINIMO = 70, ARRASTRE = 0.25;
  var x0 = 0, y0 = 0, t0 = 0, dx = 0, siguiendo = false;

  function destino(direccion) {
    var i = actual + (direccion < 0 ? 1 : -1);
    return enlaces[i] || null;
  }

  function soltar() {
    main.classList.remove("arrastrando");
    if (!reducido) {
      main.classList.add("soltando");
      setTimeout(function () { main.classList.remove("soltando"); }, 220);
    }
    main.style.transform = "";
  }

  main.addEventListener("touchstart", function (e) {
    if (e.touches.length !== 1) return;
    var t = e.touches[0];
    if (t.clientX < BORDE || t.clientX > window.innerWidth - BORDE) return;
    if (e.target.closest(IGNORAR)) return;
    x0 = t.clientX; y0 = t.clientY; t0 = Date.now(); dx = 0; siguiendo = true;
  }, { passive: true });

  main.addEventListener("touchmove", function (e) {
    if (!siguiendo) return;
    var t = e.touches[0];
    dx = t.clientX - x0;
    var dy = t.clientY - y0;
    if (Math.abs(dy) > 12 && Math.abs(dy) > Math.abs(dx)) {   // está haciendo scroll vertical: no es para nosotros
      siguiendo = false; soltar(); return;
    }
    if (!reducido && Math.abs(dx) > 10 && destino(dx)) {       // el contenido sigue al dedo, con resistencia
      main.classList.add("arrastrando");
      main.style.transform = "translateX(" + (dx * ARRASTRE) + "px)";
    }
  }, { passive: true });

  main.addEventListener("touchend", function () {
    if (!siguiendo) return;
    siguiendo = false;
    var a = destino(dx);
    if (a && Math.abs(dx) > MINIMO && Date.now() - t0 < 900) {
      window.location.href = a.href;
    } else {
      soltar();
    }
  });
  main.addEventListener("touchcancel", function () { siguiendo = false; soltar(); });
})();
