/* Edición en la misma tienda: el lápiz de las fotos, los nombres y las descripciones.
   Solo se carga para quien tiene permiso de editar productos (y el servidor lo vuelve a revisar).

   Fotos: subir desde el computador, pegar una imagen copiada (Ctrl+V) o arrastrarla encima.
   Antes de subirla se achica en el navegador (lado mayor 1600 px), así una captura pesada no falla.
   Textos: el lápiz cambia el texto por un cuadro; Guardar o Ctrl+Enter guarda, Esc cancela. */
(function () {
  'use strict';
  var LADO_MAX = 1600;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var esDemo = function () { return document.documentElement.hasAttribute('data-demo'); };
  var fotoActiva = null;   // la foto sobre la que está el mouse o cuyo menú está abierto (para Ctrl+V)
  function cerca(e, sel) { return e.target && e.target.closest ? e.target.closest(sel) : null; }

  // ── Avisos ─────────────────────────────────────────────────────────────
  function aviso(texto, tipo) {
    var a = document.querySelector('.edicion-aviso');
    if (!a) {
      a = document.createElement('div'); a.className = 'edicion-aviso';
      a.setAttribute('role', 'status'); a.setAttribute('aria-live', 'polite');
      document.body.appendChild(a);
    }
    a.textContent = texto; a.dataset.tipo = tipo || 'ok'; a.hidden = false;
    clearTimeout(aviso.t); aviso.t = setTimeout(function () { a.hidden = true; }, tipo === 'error' ? 6000 : 3000);
  }

  function enviar(url, datos) {
    if (esDemo()) {   // la demostración estática no tiene servidor
      return new Promise(function (ok) { setTimeout(function () { ok({ demo: true }); }, 350); });
    }
    return fetch(url, { method: 'POST', body: datos, credentials: 'same-origin',
                        headers: { 'X-CSRFToken': csrf, 'Accept': 'application/json' } })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok) throw new Error(j.error || (r.status === 403 ? 'No tienes permiso para editar productos.' :
                                                 'No se pudo guardar (error ' + r.status + ').'));
          return j;
        });
      }, function () { throw new Error('Sin conexión. Revisa el internet e intenta de nuevo.'); });
  }

  // ── Fotos ──────────────────────────────────────────────────────────────
  function marcoDe(caja) { return caja.matches('.foto') ? caja : caja.querySelector('.foto'); }

  function achicar(archivo) {
    // Devuelve un archivo de máximo LADO_MAX px. Si el navegador no puede, se manda el original.
    if (!window.createImageBitmap) return Promise.resolve(archivo);
    return createImageBitmap(archivo).then(function (img) {
      var escala = Math.min(1, LADO_MAX / Math.max(img.width, img.height));
      if (escala === 1 && archivo.size < 2.5 * 1024 * 1024) return archivo;
      var lienzo = document.createElement('canvas');
      lienzo.width = Math.round(img.width * escala); lienzo.height = Math.round(img.height * escala);
      lienzo.getContext('2d').drawImage(img, 0, 0, lienzo.width, lienzo.height);
      return new Promise(function (ok) {
        lienzo.toBlob(function (b) { ok(b ? new File([b], 'foto.jpg', { type: 'image/jpeg' }) : archivo); }, 'image/jpeg', 0.9);
      });
    }, function () { return archivo; });
  }

  function mostrarFoto(caja, url) {
    var marco = marcoDe(caja);
    var img = marco.querySelector('img');
    if (url) {
      if (!img) { img = document.createElement('img'); img.alt = ''; marco.insertBefore(img, marco.firstChild); }
      img.src = url;
      marco.classList.remove('sin-imagen');
    } else {
      if (img) img.remove();
      marco.classList.add('sin-imagen');
    }
  }

  function subirFoto(caja, archivo) {
    cerrarMenu();
    if (!archivo || !/^image\//.test(archivo.type)) { aviso('Eso no es una imagen. Usa JPG, PNG o WebP.', 'error'); return; }
    caja.classList.add('subiendo');
    var local = URL.createObjectURL(archivo);   // se ve de una vez, antes de que termine de subir
    var anterior = (marcoDe(caja).querySelector('img') || {}).src || '';
    mostrarFoto(caja, local);
    achicar(archivo).then(function (listo) {
      var datos = new FormData(); datos.append('foto', listo, listo.name || 'foto.jpg');
      return enviar(caja.dataset.editarFoto, datos);
    }).then(function (r) {
      if (!r.demo) mostrarFoto(caja, r.url);
      aviso(r.demo ? 'Foto puesta (en la demostración no se guarda).' : 'Foto guardada.');
    }).catch(function (e) {
      mostrarFoto(caja, anterior);
      aviso(e.message, 'error');
    }).then(function () { caja.classList.remove('subiendo'); });
  }

  function quitarFoto(caja) {
    cerrarMenu();
    if (!window.confirm('¿Quitar la foto de este producto? Se verá el logo en su lugar.')) return;
    enviar(caja.dataset.quitarFoto, new FormData()).then(function () {
      mostrarFoto(caja, ''); aviso('Foto quitada.');
    }).catch(function (e) { aviso(e.message, 'error'); });
  }

  var selector = document.createElement('input');
  selector.type = 'file'; selector.accept = 'image/jpeg,image/png,image/webp'; selector.hidden = true;
  selector.addEventListener('change', function () {
    if (selector.files[0] && selector.caja) subirFoto(selector.caja, selector.files[0]);
    selector.value = '';
  });

  var menu = null;
  function cerrarMenu() { if (menu) { menu.remove(); menu = null; } }
  function abrirMenu(caja, boton) {
    cerrarMenu();
    fotoActiva = caja;
    menu = document.createElement('div');
    menu.className = 'menu-foto'; menu.setAttribute('role', 'menu');
    var tieneFoto = !!marcoDe(caja).querySelector('img');
    menu.innerHTML =
      '<button type="button" role="menuitem" data-accion="subir">Subir desde el computador</button>' +
      '<button type="button" role="menuitem" data-accion="pegar">Pegar foto copiada <kbd>Ctrl+V</kbd></button>' +
      (tieneFoto && caja.dataset.quitarFoto ? '<button type="button" role="menuitem" data-accion="quitar" class="peligro">Quitar foto</button>' : '') +
      '<p>También puedes arrastrar la foto hasta aquí.</p>';
    caja.appendChild(menu);
    menu.querySelector('button').focus();
    menu.addEventListener('click', function (e) {
      var b = e.target.closest('[data-accion]'); if (!b) return;
      e.preventDefault(); e.stopPropagation();
      if (b.dataset.accion === 'subir') { selector.caja = caja; selector.click(); cerrarMenu(); }
      else if (b.dataset.accion === 'quitar') quitarFoto(caja);
      else pegarDesdeBoton(caja);
    });
  }

  function pegarDesdeBoton(caja) {
    // Leer el portapapeles con un clic necesita permiso del navegador; si no lo da, Ctrl+V sí funciona.
    if (!navigator.clipboard || !navigator.clipboard.read) { aviso('Presiona Ctrl+V (o Cmd+V en Mac) para pegar la foto.'); return; }
    navigator.clipboard.read().then(function (items) {
      for (var i = 0; i < items.length; i++) {
        var tipo = items[i].types.find(function (t) { return /^image\//.test(t); });
        if (tipo) return items[i].getType(tipo).then(function (b) { subirFoto(caja, new File([b], 'pegada.png', { type: tipo })); });
      }
      aviso('No hay ninguna imagen copiada. Copia una foto y vuelve a intentar.', 'error');
    }).catch(function () { aviso('Presiona Ctrl+V (o Cmd+V en Mac) para pegar la foto.'); });
  }

  document.addEventListener('paste', function (e) {
    if (!fotoActiva || cerca(e, 'input, textarea')) return;
    var archivos = Array.prototype.filter.call(e.clipboardData.files || [], function (f) { return /^image\//.test(f.type); });
    if (!archivos.length) {
      var it = Array.prototype.find.call(e.clipboardData.items || [], function (x) { return x.kind === 'file' && /^image\//.test(x.type); });
      if (it) archivos = [it.getAsFile()];
    }
    if (!archivos.length) return;
    e.preventDefault();
    subirFoto(fotoActiva, archivos[0]);
  });

  document.addEventListener('mouseover', function (e) {
    var caja = cerca(e, '[data-editar-foto]');
    if (caja) fotoActiva = caja;
  });
  document.addEventListener('mouseout', function (e) {
    var caja = cerca(e, '[data-editar-foto]');
    if (caja && !caja.contains(e.relatedTarget) && !menu) fotoActiva = null;
  });

  // Arrastrar y soltar una foto encima.
  document.addEventListener('dragover', function (e) {
    var caja = cerca(e, '[data-editar-foto]');
    if (!caja || !e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') < 0) return;
    e.preventDefault(); caja.classList.add('soltar-aqui');
  });
  document.addEventListener('dragleave', function (e) {
    var caja = cerca(e, '[data-editar-foto]');
    if (caja && !caja.contains(e.relatedTarget)) caja.classList.remove('soltar-aqui');
  });
  document.addEventListener('drop', function (e) {
    var caja = cerca(e, '[data-editar-foto]');
    if (!caja) return;
    e.preventDefault(); caja.classList.remove('soltar-aqui');
    if (e.dataTransfer.files[0]) subirFoto(caja, e.dataTransfer.files[0]);
  });

  // ── Textos ─────────────────────────────────────────────────────────────
  function pintarTexto(caja, valor) {
    var destino = caja.querySelector('.valor');
    caja.dataset.valor = valor;
    if (caja.hasAttribute('data-multilinea')) {
      destino.textContent = '';
      if (!valor) { destino.textContent = 'Sin descripción todavía. Usa el lápiz para escribirla.'; destino.classList.add('vacio'); return; }
      destino.classList.remove('vacio');
      valor.split('\n').forEach(function (linea, i) {
        if (i) destino.appendChild(document.createElement('br'));
        destino.appendChild(document.createTextNode(linea));
      });
    } else {
      destino.textContent = valor;
      // El mismo nombre puede estar en otras partes de la página (por ejemplo, la tarjeta y la vista rápida).
      document.querySelectorAll('[data-editar-texto="' + caja.dataset.editarTexto + '"] .valor').forEach(function (v) { v.textContent = valor; });
    }
  }

  function editarTexto(caja) {
    if (caja.classList.contains('editando')) return;
    var multilinea = caja.hasAttribute('data-multilinea');
    var max = Number(caja.dataset.max) || 2000;
    var original = caja.dataset.valor || '';
    var formulario = document.createElement('form');
    formulario.className = 'form-edicion';
    var campo = document.createElement(multilinea ? 'textarea' : 'input');
    campo.value = original; campo.maxLength = max;
    campo.setAttribute('aria-label', multilinea ? 'Descripción del producto' : 'Nombre del producto');
    if (multilinea) campo.rows = Math.min(12, Math.max(4, original.split('\n').length + 1));
    var pie = document.createElement('div'); pie.className = 'pie-edicion';
    pie.innerHTML = '<span class="ayuda contador"></span><button type="button" class="secundario" data-cancelar>Cancelar</button><button type="submit">Guardar</button>';
    formulario.appendChild(campo); formulario.appendChild(pie);
    caja.classList.add('editando');
    caja.appendChild(formulario);
    var contador = pie.querySelector('.contador');
    function contar() { contador.textContent = campo.value.length + ' / ' + max + (multilinea ? ' · Ctrl+Enter guarda' : ''); }
    contar(); campo.addEventListener('input', contar);
    campo.focus(); campo.setSelectionRange(campo.value.length, campo.value.length);

    function cerrar() { formulario.remove(); caja.classList.remove('editando'); caja.querySelector('[data-lapiz]').focus(); }
    pie.querySelector('[data-cancelar]').addEventListener('click', cerrar);
    campo.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); cerrar(); }
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); formulario.requestSubmit(); }
    });
    formulario.addEventListener('submit', function (e) {
      e.preventDefault(); e.stopPropagation();
      var valor = campo.value.trim();
      if (!multilinea && !valor) { aviso('El nombre no puede quedar vacío.', 'error'); return; }
      if (valor === original) { cerrar(); return; }
      var boton = pie.querySelector('[type=submit]'); boton.disabled = true; boton.textContent = 'Guardando…';
      var datos = new FormData(); datos.append('valor', valor);
      enviar(caja.dataset.editarTexto, datos).then(function (r) {
        pintarTexto(caja, r.demo ? valor : r.valor);
        cerrar();
        aviso(r.demo ? 'Cambiado (en la demostración no se guarda).' : 'Guardado.');
      }).catch(function (err) {
        aviso(err.message, 'error'); boton.disabled = false; boton.textContent = 'Guardar';
      });
    }, true);   // fase de captura: se adelanta al aviso genérico de la demostración
  }

  // ── Lápices ────────────────────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var lapiz = cerca(e, '[data-lapiz]');
    if (!lapiz) {
      if (menu && !cerca(e, '.menu-foto')) cerrarMenu();
      return;
    }
    e.preventDefault(); e.stopPropagation();
    var texto = lapiz.closest('[data-editar-texto]');
    var foto = lapiz.closest('[data-editar-foto]');
    if (texto) editarTexto(texto);
    else if (foto) { if (menu && menu.parentNode === foto) cerrarMenu(); else abrirMenu(foto, lapiz); }
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrarMenu(); });

  // Interruptor para ver la tienda sin lápices (como la ve un cliente).
  function interruptor() {
    if (!document.querySelector('[data-lapiz]') || document.querySelector('.interruptor-lapices')) return;
    var oculto = false;
    try { oculto = localStorage.getItem('lapices') === 'ocultos'; } catch (e) { /* sin almacenamiento */ }
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'interruptor-lapices';
    function pintar() {
      document.body.classList.toggle('sin-lapices', oculto);
      b.setAttribute('aria-pressed', String(!oculto));
      b.textContent = oculto ? '✎ Mostrar lápices de edición' : '✎ Edición activa · ver como cliente';
    }
    b.addEventListener('click', function () {
      oculto = !oculto; pintar();
      try { localStorage.setItem('lapices', oculto ? 'ocultos' : 'visibles'); } catch (e) { /* nada */ }
    });
    document.body.appendChild(b); pintar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', interruptor); else interruptor();
  document.body && document.body.addEventListener('htmx:afterSwap', interruptor);
})();
