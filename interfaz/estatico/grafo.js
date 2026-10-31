// T251: pestaña Grafo (al estilo del graph.html de Graphify, con su misma libreria: vis-network, en local).
// Pide /grafo/datos una vez, lo dibuja y filtra aqui mismo: filtrar solo oculta o muestra nodos (sin
// recalcular la colocacion), por eso va fluido con cientos de nodos y en el movil.
// Seguridad: todo texto de las tareas entra con textContent, nunca como HTML; sin tooltips HTML de vis.
(function () {
  "use strict";

  var FORMAS = { tarea: "dot", propuesta: "diamond", revision: "star", borrador: "square", turno: "triangle", ia: "hexagon" };
  var TAMANOS = { tarea: 10, propuesta: 11, revision: 13, borrador: 9, turno: 11, ia: 24 };
  var CONTEXTO = { turno: true, ia: true };           // sin estado ni tema propios
  var GRUPOS_VIVOS = { por_hacer: true, en_marcha: true, atascadas: true, propuestas: true };
  var ENLACES = { tarea: "Abrir la ficha completa", propuesta: "Abrir la ficha completa",
                  revision: "Abrir la ficha completa", borrador: "Abrir el borrador", turno: "Ir a Turnos",
                  ia: "Ir a Proveedores" };
  var MAX_RESULTADOS = 8;

  var datos = null, porId = {}, vecinos = {}, nodos = null, aristas = null, red = null;
  var forzados = {}, visibles = {}, seleccionado = "", colores = {};

  function $(id) { return document.getElementById(id); }

  function estado(texto) { $("grafo-estado").textContent = texto; }

  // ---------------------------------------------------------------- colores del tema actual
  function leerColores() {
    var css = window.getComputedStyle(document.documentElement);
    var claves = ["por-hacer", "aparcada", "en-marcha", "propuesta", "esperando", "atascada", "sin-comprobar",
                  "comprobada", "descartada", "turno", "ia", "otro", "linea", "seleccion"];
    colores = {};
    claves.forEach(function (c) { colores[c] = css.getPropertyValue("--g-" + c).trim() || "#888888"; });
    colores.texto = css.getPropertyValue("--texto").trim() || "#1b1f27";
    colores.fondo = css.getPropertyValue("--superficie").trim() || "#ffffff";
  }

  function aspecto(n) {
    var c = colores[n.clase] || colores.otro;
    return {
      color: { background: c, border: c, highlight: { background: c, border: colores.seleccion },
               hover: { background: c, border: colores.seleccion } },
      font: { color: colores.texto, strokeWidth: 3, strokeColor: colores.fondo, size: n.tipo === "ia" ? 16 : 13,
              face: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif" }
    };
  }

  function repintar() {
    if (!nodos) { return; }
    leerColores();
    nodos.update(datos.nodes.map(function (n) { var a = aspecto(n); a.id = n.id; return a; }));
    red.setOptions({ edges: { color: { color: colores.linea, highlight: colores.seleccion, hover: colores.seleccion } } });
  }

  // ---------------------------------------------------------------- filtros (en la URL)
  var form;
  function leerFiltros() {
    var tipos = {};
    Array.prototype.forEach.call(form.querySelectorAll('input[name="tipo"]'), function (c) {
      if (c.checked) { tipos[c.value] = true; }
    });
    return {
      q: form.elements.q.value.trim(), estado: form.elements.estado.value, tema: form.elements.tema.value,
      ia: form.elements.ia.value, desde: form.elements.desde.value, hasta: form.elements.hasta.value,
      sueltos: form.elements.sueltos.checked, tipos: tipos
    };
  }

  function ponerFiltrosDeURL() {
    var p = new URLSearchParams(window.location.search);
    ["estado", "tema", "ia", "desde", "hasta"].forEach(function (k) {
      var v = p.get(k), campo = form.elements[k];
      if (v === null) { return; }
      if (campo.tagName === "SELECT" && !Array.prototype.some.call(campo.options, function (o) { return o.value === v; })) { return; }
      campo.value = v;
    });
    form.elements.sueltos.checked = p.get("sueltos") === "1";
    var quitados = p.getAll("sin");
    Array.prototype.forEach.call(form.querySelectorAll('input[name="tipo"]'), function (c) {
      c.checked = quitados.indexOf(c.value) < 0;
    });
    if (quitados.length || p.get("tema") || p.get("ia") || p.get("desde") || p.get("hasta") || p.get("sueltos")) {
      $("grafo-mas").open = true;
    }
    return p.get("nodo") || "";
  }

  function guardarURL(f) {
    var p = new URLSearchParams();
    if (f.estado && f.estado !== "todas") { p.set("estado", f.estado); }
    ["tema", "ia", "desde", "hasta"].forEach(function (k) { if (f[k]) { p.set(k, f[k]); } });
    if (f.sueltos) { p.set("sueltos", "1"); }
    Object.keys(FORMAS).forEach(function (t) { if (!f.tipos[t]) { p.append("sin", t); } });
    if (seleccionado) { p.set("nodo", seleccionado); }
    var q = p.toString();
    window.history.replaceState(null, "", "/grafo" + (q ? "?" + q : ""));
  }

  function pasaEstado(n, f) {
    if (!n.grupo || f.estado === "todas") { return true; }
    if (f.estado === "vivas") { return !!GRUPOS_VIVOS[n.grupo]; }
    return n.grupo === f.estado;
  }

  function aplicar() {
    var f = leerFiltros();
    var porAtributo = f.estado !== "todas" || !!f.tema;
    var pasa = {};
    datos.nodes.forEach(function (n) {
      var ok = !!f.tipos[n.tipo]
        && (!f.ia || n.ias.indexOf(f.ia) >= 0)
        && (!(f.desde || f.hasta) || (n.fecha && (!f.desde || n.fecha >= f.desde) && (!f.hasta || n.fecha <= f.hasta))
            || (n.tipo === "ia"))
        && (CONTEXTO[n.tipo] || (pasaEstado(n, f) && (!f.tema || n.tema === f.tema)));
      if (ok) { pasa[n.id] = true; }
    });
    // Turnos e IAs no tienen estado ni tema: con esos filtros se ven si tocan algo que si pasa.
    if (porAtributo || f.desde || f.hasta) {
      datos.nodes.forEach(function (n) {
        if (CONTEXTO[n.tipo] && pasa[n.id] && !(vecinos[n.id] || []).some(function (v) {
          return pasa[v.id] && !CONTEXTO[porId[v.id].tipo];
        })) { delete pasa[n.id]; }
      });
    }
    visibles = {};
    datos.nodes.forEach(function (n) {
      if (!pasa[n.id]) { return; }
      // "Sin relaciones" = sin ninguna guardada (no: sin ninguna a la vista con estos filtros)
      if (f.sueltos || (vecinos[n.id] || []).length || forzados[n.id]) { visibles[n.id] = true; }
    });
    Object.keys(forzados).forEach(function (id) { visibles[id] = true; });
    nodos.update(datos.nodes.map(function (n) { return { id: n.id, hidden: !visibles[n.id] }; }));
    var nv = Object.keys(visibles).length;
    var ne = datos.links.filter(function (l) { return visibles[l.source] && visibles[l.target]; }).length;
    estado("Se ven " + nv + " de " + datos.nodes.length + " elementos y " + ne + " de " + datos.links.length +
           " relaciones." + (nv ? "" : " Ninguno con estos filtros: prueba a quitar alguno."));
    guardarURL(f);
    return nv;
  }

  function encajar() {
    var ids = Object.keys(visibles);
    if (ids.length) { red.fit({ nodes: ids, animation: { duration: 300 } }); }
  }

  // ---------------------------------------------------------------- ficha
  function mostrarFicha(id) {
    var n = porId[id];
    if (!n) { return; }
    seleccionado = id;
    $("grafo-ficha-tipo").textContent = datos.graph.tipos[n.tipo] || n.tipo;
    $("grafo-ficha-titulo").textContent = n.titulo;
    var est = $("grafo-ficha-estado");
    est.textContent = "";
    if (n.estado) {
      var punto = document.createElement("span");
      punto.className = "grafo-punto grafo-c-" + n.clase;
      punto.setAttribute("aria-hidden", "true");
      var fuerte = document.createElement("strong");
      fuerte.textContent = " " + n.estado;
      est.appendChild(punto);
      est.appendChild(fuerte);
      est.appendChild(document.createTextNode(n.frase ? ". " + n.frase : ""));
    } else {
      est.textContent = n.frase || "";
    }
    $("grafo-ficha-resumen").textContent = n.resumen || "";
    $("grafo-ficha-fecha").textContent = n.fecha ? "Última actividad: " + n.fecha.split("-").reverse().join("/") +
      (n.tema ? " · Tema: " + n.tema : "") : (n.tema ? "Tema: " + n.tema : "");
    var enlace = $("grafo-ficha-enlace");
    enlace.parentNode.hidden = !n.url;
    if (n.url) { enlace.href = n.url; enlace.textContent = ENLACES[n.tipo] || "Abrir"; }

    var lista = $("grafo-ficha-relaciones");
    lista.textContent = "";
    var rels = vecinos[id] || [];
    if (!rels.length) {
      var li0 = document.createElement("li");
      li0.textContent = "No tiene relaciones guardadas.";
      lista.appendChild(li0);
    }
    rels.slice().sort(function (a, b) { return a.texto.localeCompare(b.texto, "es"); }).forEach(function (v) {
      var otro = porId[v.id], li = document.createElement("li"), b = document.createElement("button");
      b.type = "button";
      var rel = document.createElement("span");
      rel.className = "grafo-rel";
      rel.textContent = v.texto + (otro.estado ? " · " + otro.estado : "");
      b.appendChild(rel);
      b.appendChild(document.createTextNode(otro.etiqueta));
      b.addEventListener("click", function () { seleccionar(v.id); });
      li.appendChild(b);
      lista.appendChild(li);
    });
    $("grafo-ficha").hidden = false;
    guardarURL(leerFiltros());
  }

  function cerrarFicha() {
    $("grafo-ficha").hidden = true;
    seleccionado = "";
    if (red) { red.unselectAll(); }
    guardarURL(leerFiltros());
  }

  function seleccionar(id) {
    if (!porId[id]) { return; }
    if (!visibles[id]) { forzados[id] = true; aplicar(); }
    red.selectNodes([id]);
    red.focus(id, { scale: Math.max(red.getScale(), 1.1), animation: { duration: 400 } });
    mostrarFicha(id);
    $("grafo-ficha-titulo").focus({ preventScroll: true });   // teclado: se sigue desde la ficha
  }

  // ---------------------------------------------------------------- buscador
  function buscar() {
    var aguja = form.elements.q.value.trim().toLowerCase();
    var ul = $("grafo-resultados");
    ul.textContent = "";
    if (!aguja) { ul.hidden = true; return []; }
    var hallados = datos.nodes.filter(function (n) {
      return n.id.toLowerCase() === aguja || n.titulo.toLowerCase().indexOf(aguja) >= 0;
    }).sort(function (a, b) {
      return (b.id.toLowerCase() === aguja) - (a.id.toLowerCase() === aguja) ||
             (b.titulo.toLowerCase().indexOf(aguja) === 0) - (a.titulo.toLowerCase().indexOf(aguja) === 0);
    });
    hallados.slice(0, MAX_RESULTADOS).forEach(function (n) {
      var li = document.createElement("li"), b = document.createElement("button");
      b.type = "button";
      b.textContent = n.etiqueta + (n.estado ? " — " + n.estado : "");
      b.addEventListener("click", function () { ul.hidden = true; seleccionar(n.id); });
      li.appendChild(b);
      ul.appendChild(li);
    });
    if (!hallados.length) {
      var li = document.createElement("li");
      li.textContent = "Nada coincide con «" + form.elements.q.value.trim() + "».";
      ul.appendChild(li);
    } else if (hallados.length > MAX_RESULTADOS) {
      var mas = document.createElement("li");
      mas.className = "bc-meta";
      mas.textContent = "…y " + (hallados.length - MAX_RESULTADOS) + " más: afina la búsqueda.";
      ul.appendChild(mas);
    }
    ul.hidden = false;
    return hallados;
  }

  // ---------------------------------------------------------------- montaje
  function preparar(g) {
    datos = g;
    porId = {};
    vecinos = {};
    g.nodes.forEach(function (n) { porId[n.id] = n; vecinos[n.id] = []; });
    g.links.forEach(function (l) {
      var r = g.graph.relaciones[l.tipo] || [l.tipo, l.tipo];
      vecinos[l.source].push({ id: l.target, texto: r[0] });
      vecinos[l.target].push({ id: l.source, texto: r[1] });
    });
    var tema = form.elements.tema, ia = form.elements.ia;
    g.graph.temas.forEach(function (t) { tema.add(new Option(t, t)); });
    Object.keys(g.graph.ias).forEach(function (k) { ia.add(new Option(g.graph.ias[k], k)); });
  }

  function dibujar(nodoInicial) {
    leerColores();
    nodos = new window.vis.DataSet(datos.nodes.map(function (n) {
      var a = aspecto(n);
      a.id = n.id;
      a.label = n.etiqueta;
      a.shape = FORMAS[n.tipo] || "dot";
      a.size = TAMANOS[n.tipo] || 10;
      a.hidden = true;
      return a;
    }));
    aristas = new window.vis.DataSet(datos.links.map(function (l, i) {
      return { id: i, from: l.source, to: l.target, dashes: l.tipo === "junto" || l.tipo === "espera" };
    }));
    red = new window.vis.Network($("grafo-lienzo"), { nodes: nodos, edges: aristas }, {
      autoResize: true,
      layout: { improvedLayout: false, randomSeed: 42 },
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: { gravitationalConstant: -40, centralGravity: 0.012, springLength: 70, springConstant: 0.08,
                            avoidOverlap: 0.4 },
        maxVelocity: 60, minVelocity: 1,
        stabilization: { enabled: true, iterations: 350, updateInterval: 35, fit: false }
      },
      interaction: { hover: true, hideEdgesOnDrag: true, multiselect: false, navigationButtons: false,
                     keyboard: false, tooltipDelay: 3600000 },
      nodes: { borderWidth: 1, borderWidthSelected: 3, scaling: { label: { drawThreshold: 10 } } },
      edges: { arrows: { to: { enabled: true, scaleFactor: 0.45 } }, smooth: false, width: 1, selectionWidth: 2,
               color: { color: colores.linea, highlight: colores.seleccion, hover: colores.seleccion, opacity: 0.85 } }
    });
    aplicar();
    red.on("stabilizationProgress", function (p) {
      estado("Colocando los elementos… " + Math.round(100 * p.iterations / p.total) + " %");
    });
    red.once("stabilizationIterationsDone", function () {
      red.setOptions({ physics: false });   // ya colocado: filtrar y moverse no recalcula nada
      aplicar();
      if (nodoInicial && porId[nodoInicial]) { seleccionar(nodoInicial); } else { encajar(); }
    });
    red.on("click", function (p) {
      if (p.nodes.length) { mostrarFicha(p.nodes[0]); } else if (!p.edges.length) { cerrarFicha(); }
    });
  }

  function cargar() {
    estado("Cargando el grafo…");
    fetch("/grafo/datos", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) { throw new Error(j && j.error ? j.error : "HTTP " + r.status); }
          return j;
        });
      })
      .then(function (g) {
        if (!window.vis) { throw new Error("No se ha cargado la librería del grafo."); }
        preparar(g);
        var nodoInicial = ponerFiltrosDeURL();
        dibujar(nodoInicial);
      })
      .catch(function (e) {
        var p = $("grafo-estado");
        p.textContent = "No se ha podido cargar el grafo (" + (e && e.message ? e.message : "error") + "). ";
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = "Reintentar";
        b.addEventListener("click", function () { window.location.reload(); });
        p.appendChild(b);
      });
  }

  function iniciar() {
    form = $("grafo-filtros");
    if (!form) { return; }
    form.addEventListener("submit", function (e) { e.preventDefault(); var h = buscar(); if (h.length) { $("grafo-resultados").hidden = true; seleccionar(h[0].id); } });
    form.addEventListener("change", function (e) { if (datos && e.target.name !== "q") { forzados = {}; aplicar(); encajar(); } });
    var espera = 0;
    form.elements.q.addEventListener("input", function () {
      window.clearTimeout(espera);
      espera = window.setTimeout(function () { if (datos) { buscar(); } }, 200);
    });
    $("grafo-cerrar").addEventListener("click", cerrarFicha);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("grafo-ficha").hidden) { cerrarFicha(); } });
    Array.prototype.forEach.call(document.querySelectorAll("[data-zoom]"), function (b) {
      b.addEventListener("click", function () {
        if (!red) { return; }
        var z = b.getAttribute("data-zoom");
        if (z === "encajar") { encajar(); return; }
        red.moveTo({ scale: red.getScale() * (z === "mas" ? 1.4 : 1 / 1.4), animation: { duration: 200 } });
      });
    });
    // Tema claro/oscuro: el lienzo es canvas, hay que repintarlo a mano.
    new MutationObserver(repintar).observe(document.documentElement, { attributes: true, attributeFilter: ["data-tema"] });
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      if (mq.addEventListener) { mq.addEventListener("change", repintar); }
    }
    // SSE: si NEXO cambia tareas mientras se mira, se avisa (no se redibuja solo: moveria todo).
    document.body.addEventListener("nexo:tareas", function () { $("grafo-cambios").hidden = false; });
    $("grafo-recargar").addEventListener("click", function () { window.location.reload(); });
    cargar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
