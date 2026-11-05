/* Demostración estática: nada se guarda; lo que no se exportó avisa en vez de fallar.
   Inicio de sesión de mentira: con las cuentas de ejemplo se pasa a las pantallas de ese rol. */
(function () {
  var CUENTAS = {"ana@demo.co": ["cliente", "Cliente"], "empleado@demo.co": ["empleado", "Empleado"], "subjefe@demo.co": ["subjefe", "Subjefe"], "jefe@demo.co": ["jefe", "Jefe"]};   // correo → carpeta del rol (Fran y el Ingeniero no están en la demo)
  var CLAVE = "Demo-AutoPartes-2026";
  var guion = document.currentScript || document.querySelector('script[src*="demo/demo.js"]');
  var RAIZ = new URL('../../', guion.src).href;   // carpeta de la demostración

  function aviso(texto) {
    var a = document.querySelector('.demo-aviso');
    if (!a) { a = document.createElement('div'); a.className = 'demo-aviso'; a.setAttribute('role', 'status'); document.body.appendChild(a); }
    a.textContent = texto; a.hidden = false;
    clearTimeout(aviso.t); aviso.t = setTimeout(function () { a.hidden = true; }, 4500);
  }
  function existe(url) {
    return fetch(url, { method: 'HEAD' }).then(function (r) { return r.ok; }, function () { return false; });
  }
  function irComo(rol, siguiente) {
    var panel = RAIZ + rol + '/cuenta/panel/index.html';
    if (!siguiente || siguiente.charAt(0) !== '/') { window.location.href = panel; return; }
    var destino = RAIZ + rol + siguiente.replace(/\/?$/, '/') + 'index.html';
    existe(destino).then(function (ok) { window.location.href = ok ? destino : panel; });
  }
  function esLogin(form) {
    return form.querySelector('input[name=email]') && form.querySelector('input[name=password]');
  }
  function esSalir(form) { return /cuenta\/salir\/?$/.test(form.getAttribute('action') || ''); }

  // En la pantalla de Entrar, un recuadro con las cuentas de ejemplo (clic = se llenan solas).
  document.addEventListener('DOMContentLoaded', function () {
    var form = Array.prototype.find.call(document.forms, esLogin);
    if (!form) return;
    var caja = document.createElement('div');
    caja.className = 'demo-cuentas';
    var html = '<strong>Cuentas de la demostración</strong><span>Contraseña de todas: <code>' + CLAVE + '</code></span><ul>';
    Object.keys(CUENTAS).forEach(function (c) {
      html += '<li><button type="button" class="boton-link" data-correo="' + c + '">' + c + '</button> · ' + CUENTAS[c][1] + '</li>';
    });
    caja.innerHTML = html + '</ul>';
    form.parentNode.insertBefore(caja, form);
    caja.addEventListener('click', function (e) {
      var b = e.target.closest('[data-correo]');
      if (!b) return;
      form.querySelector('input[name=email]').value = b.getAttribute('data-correo');
      form.querySelector('input[name=password]').value = CLAVE;
      form.querySelector('button[type=submit]').focus();
    });
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    e.preventDefault();
    if (esSalir(form)) { window.location.href = RAIZ + 'visitante/index.html'; return; }
    if (esLogin(form)) {
      var correo = form.querySelector('input[name=email]').value.trim().toLowerCase();
      var clave = form.querySelector('input[name=password]').value;
      var cuenta = CUENTAS[correo];
      if (!cuenta || clave !== CLAVE) { aviso('Correo o contraseña incorrectos. Usa una de las cuentas de la demostración.'); return; }
      var sig = form.querySelector('input[name=next]');
      irComo(cuenta[0], sig && sig.value);
      return;
    }
    aviso('Esto es una demostración: aquí no se guarda ni se busca nada. En el sitio real esta acción funciona.');
  }, true);

  document.addEventListener('click', function (e) {
    var el = e.target.closest('a[href="#demo-no-disponible"], [data-demo-ir]');
    if (!el) return;
    var destino = el.getAttribute('data-demo-ir') || el.getAttribute('href');
    e.preventDefault();
    if (destino && destino !== '#demo-no-disponible') { window.location.href = destino; return; }
    aviso('Esta pantalla no está incluida en la demostración. En el sitio real sí funciona.');
  }, true);
})();
