// NEXO interfaz: tema (oscuro por defecto, claro opcional; Damian 12/10) y componentes Alpine.
// Se carga SIN defer en <head> para aplicar el tema antes de pintar. Alpine es el build CSP:
// nada de expresiones con logica en el HTML, todo va registrado aqui con Alpine.data().
(function () {
  "use strict";

  var CLAVE_TEMA = "nexo.tema";
  var TEMAS = ["oscuro", "claro"];

  // Lo guardado antes como "sistema" (o nada) pasa a oscuro: es el defecto desde el 12/10.
  function leerTema() {
    try {
      var t = window.localStorage.getItem(CLAVE_TEMA);
      return TEMAS.indexOf(t) >= 0 ? t : "oscuro";
    } catch (e) {
      return "oscuro";
    }
  }

  function aplicarTema(t) {
    document.documentElement.setAttribute("data-tema", t);
    try { window.localStorage.setItem(CLAVE_TEMA, t); } catch (e) { /* sin almacenamiento: vale igual */ }
  }

  aplicarTema(leerTema());

  document.addEventListener("alpine:init", function () {
    window.Alpine.data("tema", function () {
      return {
        actual: leerTema(),
        get etiqueta() { return this.actual === "oscuro" ? "Modo claro" : "Modo oscuro"; },
        cambiar: function () {
          this.actual = TEMAS[(TEMAS.indexOf(this.actual) + 1) % TEMAS.length];
          aplicarTema(this.actual);
        }
      };
    });

    // Notificaciones push de ESTE dispositivo (pantalla Ajustes, hito movil).
    window.Alpine.data("notificaciones", function () {
      return {
        estado: "cargando",   // cargando | no_compatible | bloqueadas | desactivadas | activadas
        mensaje: "",
        ocupado: false,
        get etiqueta() {
          return {
            cargando: "Comprobando…",
            no_compatible: "Este navegador no admite notificaciones aquí.",
            bloqueadas: "Bloqueadas en el navegador.",
            desactivadas: "Desactivadas.",
            activadas: "Activadas."
          }[this.estado];
        },
        get ocultoActivar() { return this.estado !== "desactivadas"; },
        get ocultoActivas() { return this.estado !== "activadas"; },
        init: function () {
          var self = this;
          if (!pushCompatible()) { this.estado = "no_compatible"; return; }
          if (Notification.permission === "denied") {
            this.estado = "bloqueadas";
            this.mensaje = "Permítelas en los ajustes del sitio de Chrome y recarga.";
            return;
          }
          suscripcionActual().then(function (sub) {
            self.estado = sub ? "activadas" : "desactivadas";
            // Por si el servidor la perdio (caducada, claves nuevas...): darla de alta otra vez no duplica.
            if (sub) { return postJSON("/push/suscribir", sub.toJSON()); }
          }).catch(function (e) {
            if (self.estado === "cargando") {
              self.estado = "no_compatible";
              self.mensaje = "(" + (e && e.message ? e.message : "error desconocido") + ")";
            }
          });
        },
        activar: function () {
          var self = this;
          this.ocupado = true;
          this.mensaje = "";
          Notification.requestPermission().then(function (permiso) {
            if (permiso !== "granted") {
              self.estado = permiso === "denied" ? "bloqueadas" : "desactivadas";
              self.mensaje = "Sin permiso no se pueden enviar avisos.";
              throw null;
            }
            return fetch("/push/clave", { credentials: "same-origin" }).then(function (r) { return r.json(); });
          }).then(function (d) {
            return swListo().then(function (reg) {
              return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: claveBytes(d.clave) });
            });
          }).then(function (sub) {
            return postJSON("/push/suscribir", sub.toJSON());
          }).then(function () {
            self.estado = "activadas";
            self.mensaje = "Pulsa «Enviar prueba» para comprobarlo.";
          }).catch(function (e) {
            if (e) { self.mensaje = "No se pudo activar: " + (e.message || e); }
          }).then(function () { self.ocupado = false; });
        },
        desactivar: function () {
          var self = this;
          this.ocupado = true;
          suscripcionActual().then(function (sub) {
            if (!sub) { return; }
            return postJSON("/push/baja", { endpoint: sub.endpoint }).then(function () { return sub.unsubscribe(); });
          }).then(function () {
            self.estado = "desactivadas";
            self.mensaje = "";
          }).catch(function (e) {
            self.mensaje = "No se pudo desactivar: " + (e.message || e);
          }).then(function () { self.ocupado = false; });
        },
        probar: function () {
          var self = this;
          this.ocupado = true;
          postJSON("/push/prueba", {}).then(function (d) {
            self.mensaje = d.enviados > 0 ? "Prueba enviada a " + d.enviados + " dispositivo(s)." :
              "No se entregó a ningún dispositivo (" + d.caducadas + " caducadas, " + d.fallos + " fallos).";
          }).catch(function (e) {
            self.mensaje = "No se pudo enviar: " + (e.message || e);
          }).then(function () { self.ocupado = false; });
        }
      };
    });

    // Doble confirmacion (PARADA / Seguir): primer clic abre el panel, el envio es el segundo.
    window.Alpine.data("confirmacion", function () {
      return {
        abierto: false,
        get cerrado() { return !this.abierto; },
        abrir: function () {
          // Un error anterior ocuparia el mismo sitio que el panel: al reintentar, fuera.
          var viejo = this.$el.querySelector(".error-parada");
          if (viejo) { viejo.remove(); }
          this.abierto = true;
          var self = this;
          this.$nextTick(function () { if (self.$refs.primero) { self.$refs.primero.focus(); } });
        },
        cancelar: function () {
          if (!this.abierto) { return; }
          this.abierto = false;
          var self = this;
          this.$nextTick(function () {
            var b = self.$el.querySelector(":scope > button");
            if (b) { b.focus(); }
          });
        }
      };
    });
  });

  // ------------------------------------------------ push (Ajustes)
  function pushCompatible() {
    return window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window &&
      "Notification" in window;
  }

  // serviceWorker.ready NUNCA se resuelve si el SW no se pudo registrar: con plazo, para que
  // Ajustes diga que pasa en vez de quedarse en "Comprobando…" (y los botones no queden bloqueados).
  var PLAZO_SW_MS = 10000;
  function swListo() {
    return new Promise(function (ok, mal) {
      var t = setTimeout(function () {
        mal(new Error("el service worker no se ha podido instalar en este navegador"));
      }, PLAZO_SW_MS);
      navigator.serviceWorker.ready.then(function (reg) { clearTimeout(t); ok(reg); });
    });
  }

  function suscripcionActual() {
    return swListo().then(function (reg) { return reg.pushManager.getSubscription(); });
  }

  function csrfToken() {
    try { return JSON.parse(document.body.getAttribute("hx-headers"))["X-CSRF-Token"]; } catch (e) { return ""; }
  }

  function postJSON(url, datos) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
      body: JSON.stringify(datos)
    }).then(function (r) {
      actualizarCsrf(r.headers.get("X-Nexo-CSRF"));
      if (!r.ok) { throw new Error("código " + r.status); }
      return r.json();
    });
  }

  // applicationServerKey: base64url -> bytes.
  function claveBytes(b64) {
    var s = (b64 + "===".slice((b64.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    var bin = window.atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) { out[i] = bin.charCodeAt(i); }
    return out;
  }

  // ------------------------------------------------ errores de peticiones HTMX
  function errorGlobal(texto) {
    var caja = document.getElementById("error-global");
    if (!caja) { return; }
    caja.textContent = texto;
    caja.hidden = !texto;
  }

  function textoError(estado) {
    if (estado === 401) { return "La sesión ha caducado (¿se reinició la web?). Vuelve a abrir NEXO con abrir_nexo.bat."; }
    if (estado === 403) { return "Petición rechazada por seguridad (CSRF/origen). Recarga la página y reintenta."; }
    if (estado === 0) { return "No hay conexión con la web de NEXO. Reintenta cuando vuelva."; }
    return "La acción no se ha podido completar (código " + estado + "). Reintenta.";
  }

  // Tras un fallo en PARADA/Seguir se vuelve a pintar el boton desde la bandera REAL.
  function refrescarParada() {
    if (window.htmx && document.getElementById("parada")) {
      window.htmx.ajax("GET", "/parada/estado", { target: "#parada", swap: "outerHTML" });
    }
  }

  // Solo tras un POST de PARADA/Seguir fallido. Nunca tras el GET de refresco (si no, un 401 o
  // un servidor caido lo relanzaria en bucle) ni con 401 (sin sesion el GET tambien fallaria).
  function tocaRefrescar(e, estado) {
    var cfg = e.detail.requestConfig || {};
    return estado !== 401 && (cfg.verb || "").toLowerCase() === "post" &&
      (cfg.path === "/parada" || cfg.path === "/seguir");
  }

  document.addEventListener("htmx:beforeRequest", function (e) {
    errorGlobal("");
    // Solo en acciones (POST): vaciar la region viva para que un aviso identico al anterior se
    // vuelva a anunciar. Un GET de refresco no debe borrar un anuncio que aun se esta leyendo.
    var verbo = ((e.detail.requestConfig || {}).verb || "").toLowerCase();
    var avisos = document.getElementById("avisos");
    if (avisos && verbo && verbo !== "get") { avisos.textContent = ""; }
  });

  // Un panel que no llega (red caida, 401...) no se queda en "cargando" para siempre: estado de
  // error con reintento. Los fallos del SERVIDOR ya vienen como panel de error (200).
  function panelConError(e, estado) {
    var panel = e.detail.target;
    if (!panel || !panel.hasAttribute || !panel.hasAttribute("data-panel")) { return; }
    var url = (e.detail.requestConfig || {}).path || panel.getAttribute("hx-get");
    var caja = document.createElement("div");
    caja.className = "estado-error";
    caja.setAttribute("role", "alert");
    var p = document.createElement("p");
    p.textContent = textoError(estado);
    var b = document.createElement("button");
    b.type = "button";
    b.className = "boton-sutil";
    b.textContent = "Reintentar";
    b.setAttribute("hx-get", url);
    b.setAttribute("hx-target", "closest [data-panel]");
    caja.appendChild(p);
    caja.appendChild(b);
    panel.replaceChildren(caja);
    if (window.htmx) { window.htmx.process(caja); }
  }

  // ------------------------------------------------ CSRF de la sesion actual
  // Cada respuesta con sesion trae X-Nexo-CSRF. Si la web se reinicio y la sesion se renovo por
  // identidad de Tailscale, la pagina pasa a usar el token nuevo sin recargar.
  function actualizarCsrf(token) {
    if (!token || !document.body) { return; }
    var actual = {};
    try { actual = JSON.parse(document.body.getAttribute("hx-headers") || "{}"); } catch (e) { actual = {}; }
    if (actual["X-CSRF-Token"] === token) { return; }
    actual["X-CSRF-Token"] = token;
    document.body.setAttribute("hx-headers", JSON.stringify(actual));
  }

  function cabecera(xhr, nombre) {
    try { return xhr ? xhr.getResponseHeader(nombre) : null; } catch (e) { return null; }
  }

  document.addEventListener("htmx:afterRequest", function (e) {
    actualizarCsrf(cabecera(e.detail.xhr, "X-Nexo-CSRF"));
  });

  document.addEventListener("htmx:responseError", function (e) {
    var estado = e.detail.xhr ? e.detail.xhr.status : 0;
    if (estado === 403 && cabecera(e.detail.xhr, "X-Nexo-Sesion-Nueva") === "1") {
      // Sesion renovada en ESTA peticion: el token ya esta al dia, pero la accion NO se repite
      // sola (acciones de autoridad: nada de reintentos a ciegas).
      errorGlobal("La web se reinició y la sesión se ha renovado: vuelve a pulsar.");
      panelConError(e, estado);
      if (tocaRefrescar(e, estado)) { refrescarParada(); }
      return;
    }
    errorGlobal(textoError(estado));
    panelConError(e, estado);
    if (tocaRefrescar(e, estado)) { refrescarParada(); }
  });

  document.addEventListener("htmx:sendError", function (e) {
    errorGlobal(textoError(0));
    panelConError(e, 0);
    if (tocaRefrescar(e, 0)) { refrescarParada(); }
  });

  // ------------------------------------------------------------ tiempo real (SSE)
  // La extension sse de htmx abre y reabre la conexion; los eventos de negocio se cogen aqui
  // y se reemiten en <body> como "nexo:<tipo>" (las pantallas usan hx-trigger="nexo:x from:body").
  var TIPOS_SSE = ["parada", "tareas", "log", "borrador", "orden", "aviso", "reconciliar", "logs_perdidos", "chat",
                   "turno", "turno_estado", "aprobacion"];
  var ultimoId = "";
  var conexionPerdida = false;

  // Si la extension tiene que CREAR otro EventSource (tras un 401/500 no reintenta el navegador
  // solo), que pida desde el ultimo id recibido y no desde el de cuando se pinto la pagina.
  document.addEventListener("DOMContentLoaded", function () {
    if (!window.htmx || !window.htmx.createEventSource) { return; }
    var crear = window.htmx.createEventSource;
    window.htmx.createEventSource = function (url) {
      if (ultimoId) { url = url.replace(/([?&]desde=)[^&]*/, "$1" + encodeURIComponent(ultimoId)); }
      return crear(url);
    };
  });

  function avisar(texto) {
    var avisos = document.getElementById("avisos");
    if (avisos) { avisos.textContent = texto; }
  }

  // causa: "red" (se reintenta solo) o "sesion" (la web se reinicio: hay que volver a entrar).
  function mostrarConexion(ok, causa) {
    var banner = document.getElementById("conexion");
    if (!banner) { return; }
    banner.hidden = ok;
    var partes = banner.querySelectorAll("[data-causa]");
    for (var i = 0; i < partes.length; i++) {
      partes[i].hidden = partes[i].getAttribute("data-causa") !== (causa || "red");
    }
  }

  // EventSource no dice el codigo HTTP: si el SSE cae, preguntar a una ruta con sesion.
  // Un 401 significa que reintentar no sirve (sesion perdida al reiniciarse la web).
  var sondeando = false;
  function comprobarSesion() {
    if (sondeando || !window.fetch) { return; }
    sondeando = true;
    window.fetch("/parada/estado", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        if (r.status === 401 && conexionPerdida) {
          mostrarConexion(false, "sesion");
          avisar("La sesión ha caducado: vuelve a abrir NEXO con abrir_nexo.bat.");
        }
      })
      .catch(function () { /* sin red: el banner de conexion ya lo dice */ })
      .then(function () { sondeando = false; });
  }

  // Estado entero de nuevo: tras reconectar o si el servidor no puede reenviar lo perdido.
  function reconciliar() {
    refrescarParada();
    document.body.dispatchEvent(new CustomEvent("nexo:reconciliar"));
  }

  // PARADA puesta o quitada desde fuera (Telegram, a mano...): repintar desde la bandera real
  // y anunciarlo, salvo que el propio boton tenga una peticion en vuelo (su respuesta ya trae
  // el estado real) o ya muestre ese estado.
  function comprobarParada(datos) {
    var w = document.getElementById("parada");
    if (!w || !window.htmx) { return; }
    if (w.classList.contains("htmx-request") || w.querySelector(".htmx-request")) { return; }
    if ((w.getAttribute("data-activa") === "1") === Boolean(datos.activa) &&
        (w.getAttribute("data-motivo") || "") === (datos.motivo || "")) { return; }
    window.htmx.ajax("GET", "/parada/estado?anunciar=1", { target: "#parada", swap: "outerHTML" });
  }

  // Tarjeta de una orden de la web: se repinta desde el servidor (su estado real); al terminar,
  // la respuesta trae ademas el aviso para el lector de pantalla.
  var FINALES_ORDEN = ["hecha", "error", "cancelada"];
  function refrescarOrden(id, anunciar) {
    var tarjeta = document.getElementById("orden-" + id);
    if (!tarjeta || !window.htmx) { return; }
    // Si la tarjeta ya se ve terminada, el evento es un replay tras reconectar: ni se repinta
    // ni se vuelve a anunciar algo que ya se anuncio.
    var yaFinal = FINALES_ORDEN.some(function (e) { return tarjeta.classList.contains("orden-" + e); });
    if (yaFinal) { return; }
    window.htmx.ajax("GET", "/ordenes/" + encodeURIComponent(id) + (anunciar ? "?anunciar=1" : ""),
      { target: tarjeta, swap: "outerHTML" });
  }

  function recibir(tipo, mensaje) {
    if (mensaje.lastEventId) { ultimoId = mensaje.lastEventId; }
    var datos = {};
    try { datos = JSON.parse(mensaje.data || "{}"); } catch (err) { datos = {}; }
    if (tipo === "reconciliar") { reconciliar(); return; }
    if (tipo === "parada") { comprobarParada(datos); }
    if (tipo === "orden" && datos.id) { refrescarOrden(datos.id, FINALES_ORDEN.indexOf(datos.estado) >= 0); }
    document.body.dispatchEvent(new CustomEvent("nexo:" + tipo, { detail: { id: mensaje.lastEventId, datos: datos } }));
  }

  document.addEventListener("htmx:sseOpen", function (e) {
    var fuente = e.detail.source;
    if (fuente && !fuente.nexoEscuchando) {
      fuente.nexoEscuchando = true;
      TIPOS_SSE.forEach(function (tipo) {
        fuente.addEventListener(tipo, function (m) { recibir(tipo, m); });
      });
    }
    mostrarConexion(true);
    if (conexionPerdida) {
      conexionPerdida = false;
      avisar("Conexión en tiempo real recuperada.");
      reconciliar();
    }
  });

  document.addEventListener("htmx:sseError", function () {
    if (!conexionPerdida) {
      avisar("Conexión en tiempo real perdida. Reintentando.");
      mostrarConexion(false, "red");
    }
    conexionPerdida = true;
    comprobarSesion();
  });

  // Formulario de orden aceptada (sin HX-Retarget = no fue rechazada): vaciarlo y dejar el foco
  // en el texto. Y repintar la tarjeta nueva una vez: el evento SSE de "en curso" pudo llegar
  // antes de que la tarjeta existiera en la pagina y se habria quedado en "en cola".
  document.addEventListener("htmx:afterRequest", function (e) {
    var form = e.detail.elt;
    if (!form || !form.hasAttribute || !form.hasAttribute("data-limpiar") || !e.detail.successful) { return; }
    if (e.detail.xhr && e.detail.xhr.getResponseHeader("HX-Retarget")) { return; }
    form.reset();
    var texto = form.querySelector("textarea");
    if (texto) { texto.focus(); }
    var nueva = document.querySelector("#ordenes-sesion > li[data-orden]");
    if (nueva) { window.setTimeout(function () { refrescarOrden(nueva.getAttribute("data-orden"), false); }, 300); }
  });

  // Tras una accion sobre una tarea se repinta la ficha entera: el foco va a su encabezado
  // (el aviso ya se anuncia por #avisos) en vez de perderse en <body>.
  document.addEventListener("htmx:afterSettle", function (e) {
    var cfg = e.detail.requestConfig || {};
    if ((cfg.verb || "").toLowerCase() !== "post" || !e.detail.target || e.detail.target.id !== "detalle-tarea") { return; }
    var titulo = document.getElementById("t-ficha");
    if (titulo) { titulo.focus(); }
  });

  // Formulario de ordenes: con PARADA se deshabilita el fieldset (sin reemplazarlo: lo escrito se
  // conserva). La verdad la manda el aviso #bloqueo-orden que pinta el servidor (data-activa).
  function sincronizarBloqueoOrden() {
    var aviso = document.getElementById("bloqueo-orden");
    var campos = document.querySelector(".form-orden fieldset");
    if (aviso && campos) { campos.disabled = aviso.getAttribute("data-activa") === "1"; }
  }
  document.addEventListener("htmx:afterSettle", function (e) {
    var cfg = e.detail.requestConfig || {};
    if ((cfg.path || "").indexOf("/ordenes/bloqueo") === 0) { sincronizarBloqueoOrden(); }
  });

  // El boton de PARADA se sustituye entero: devolver el foco a el para no perderlo en <body>.
  document.addEventListener("htmx:afterSettle", function (e) {
    var ruta = e.detail.requestConfig ? e.detail.requestConfig.path : "";
    if (ruta !== "/parada" && ruta !== "/seguir") { return; }
    var b = document.querySelector("#parada > button");
    if (b) { b.focus(); }
  });

  // T667: boton "Copiar orden" (bandeja de Claude). data-copiar = selector del <textarea> con el texto fijo.
  // Sin portapapeles (http sin contexto seguro), deja el texto seleccionado para copiarlo a mano.
  document.addEventListener("click", function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest("[data-copiar]") : null;
    if (!b) { return; }
    var origen = document.querySelector(b.getAttribute("data-copiar"));
    if (!origen) { return; }
    var estado = b.parentNode.querySelector("[data-copiar-estado]");
    function avisar(ok) {
      if (estado) {
        estado.textContent = ok ? (b.getAttribute("data-copiado") || "Orden copiada: pégala en Claude Code.") :
          "No se pudo copiar solo: el texto queda seleccionado, cópialo a mano.";
        if (b.hasAttribute("data-copiado")) {   // indicador de Claude: el aviso se apaga solo
          setTimeout(function () { estado.textContent = ""; }, 4000);
        }
      }
    }
    function aMano() {
      if (origen.select) { origen.select(); }
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      avisar(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
      navigator.clipboard.writeText(origen.value || origen.textContent || "").then(function () { avisar(true); }, aMano);
    } else {
      aMano();
    }
  });

  // App instalable (hito movil): el service worker solo guarda estaticos y la pagina "sin conexion".
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () { /* sin SW la web funciona igual */ });
    });
  }
})();
