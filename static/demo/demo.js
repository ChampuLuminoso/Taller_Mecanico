/* Demostración estática: nada se guarda; lo que no se exportó avisa en vez de fallar. */
(function () {
  function aviso(texto) {
    var a = document.querySelector('.demo-aviso');
    if (!a) { a = document.createElement('div'); a.className = 'demo-aviso'; a.setAttribute('role', 'status'); document.body.appendChild(a); }
    a.textContent = texto; a.hidden = false;
    clearTimeout(aviso.t); aviso.t = setTimeout(function () { a.hidden = true; }, 3800);
  }
  document.addEventListener('submit', function (e) {
    e.preventDefault();
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
