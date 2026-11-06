/* En el celular, las tablas anchas (4 columnas o más) se ven como tarjetas: cada fila es un bloque y cada
   dato lleva el nombre de su columna al lado. Aquí solo se copia el título de la columna a cada celda
   (data-columna); el cambio de forma lo hace el CSS (table.apilada). Sin JavaScript, la tabla se desliza
   de lado como antes. */
(function () {
  function preparar(raiz) {
    (raiz || document).querySelectorAll('main table:not(.apilada):not(.no-apilar)').forEach(function (tabla) {
      var titulos = Array.prototype.map.call(tabla.querySelectorAll('thead th'), function (th) { return th.textContent.trim(); });
      if (titulos.length < 4) return;
      tabla.querySelectorAll('tbody tr').forEach(function (fila) {
        var col = 0;
        Array.prototype.forEach.call(fila.children, function (celda) {
          if (!celda.hasAttribute('data-columna')) celda.setAttribute('data-columna', titulos[col] || '');
          col += celda.colSpan || 1;
        });
      });
      tabla.classList.add('apilada');
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { preparar(); });
  else preparar();
  document.addEventListener('htmx:afterSwap', function (e) { preparar(e.target); });
})();
