/* Aviso "Abierto ahora / Cerrado" de la página de inicio.
   El servidor ya lo escribe al armar la página; este script lo vuelve a calcular cada minuto con la hora de
   Bogotá (sin importar la zona horaria del celular), por si la página se queda abierta un buen rato.
   Usa los próximos 60 días que manda el servidor ya resueltos: horario, festivos y días cerrados. */
(function () {
  var nodo = document.getElementById('estado-taller');
  var datos = document.getElementById('calendario-taller');
  if (!nodo || !datos) return;
  var dias;
  try { dias = JSON.parse(datos.textContent); } catch (e) { return; }
  var NOMBRES = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  var formato = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

  function ahoraBogota() {
    var p = {};
    formato.formatToParts(new Date()).forEach(function (x) { p[x.type] = x.value; });
    return { fecha: p.year + '-' + p.month + '-' + p.day, hhmm: p.hour + ':' + p.minute };
  }
  function sumarDias(iso, n) {
    var d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  function hora(hhmm) {   // "13:00" → "1:00 p. m."
    var h = Number(hhmm.slice(0, 2));
    return (h % 12 || 12) + ':' + hhmm.slice(3) + (h < 12 ? ' a. m.' : ' p. m.');
  }
  function calcular() {
    var a = ahoraBogota(), hoy = dias[a.fecha], t = a.hhmm;
    if (hoy === undefined) return null;   // la página es muy vieja: se deja lo que escribió el servidor
    if (Array.isArray(hoy)) {
      if (t < hoy[0]) return ['cerrado', 'Hoy abrimos a las ' + hora(hoy[0])];
      if (hoy[2] && hoy[2] <= t && t < hoy[3]) return ['cerrado', 'En almuerzo · volvemos a las ' + hora(hoy[3])];
      if (t < hoy[1]) return ['abierto', 'Abierto ahora · hasta las ' + hora(hoy[1])];
    }
    var motivo = typeof hoy === 'string' ? hoy : '';
    for (var i = 1; i < 15; i++) {
      var f = sumarDias(a.fecha, i), dia = dias[f];
      if (dia === undefined) break;
      if (Array.isArray(dia)) {
        var d = new Date(f + 'T12:00:00Z');
        var cuando = i === 1 ? 'mañana' : i < 7 ? 'el ' + NOMBRES[d.getUTCDay()] : 'el ' + d.getUTCDate() + ' de ' + MESES[d.getUTCMonth()];
        return ['cerrado', (motivo ? 'Hoy es ' + motivo : 'Cerrado ahora') + ' · abrimos ' + cuando + ' a las ' + hora(dia[0])];
      }
    }
    return ['cerrado', 'Cerrado ahora'];
  }
  function pintar() {
    var r = calcular();
    if (!r) return;
    nodo.className = 'estado-taller ' + r[0];
    var texto = nodo.querySelector('.texto');
    if (texto.textContent !== r[1]) texto.textContent = r[1];
  }
  pintar();
  setInterval(pintar, 60 * 1000);
})();
