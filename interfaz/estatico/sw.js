// Service worker de NEXO (hito movil). Se sirve en /sw.js (alcance "/") desde interfaz/rutas/pwa.py.
//
// REGLA: NUNCA se guarda en cache nada con datos privados. Solo:
//   - la pagina /sin-conexion (sin datos) y
//   - los ficheros de /estatico/ (CSS, JS, iconos: iguales para todos).
// Las paginas (HTML con tareas, ordenes, logs...), /eventos (SSE) y las respuestas de HTMX van
// SIEMPRE a la red y ni se miran: si falla la red en una navegacion, se muestra /sin-conexion.
"use strict";

var VERSION = "nexo-v8";   // v8 (T691 escritorio): nexo.css con diseno de pantalla ancha
var SIN_CONEXION = "/sin-conexion";
var ESENCIALES = [
  SIN_CONEXION,
  "/estatico/nexo.css",
  "/estatico/nexo.js",
  "/estatico/vendor/htmx.min.js",
  "/estatico/vendor/sse.min.js",
  "/estatico/vendor/alpine-csp.min.js",
  "/estatico/iconos/nexo-192.png"
];

function esEstatico(url) {
  return url.origin === self.location.origin && url.pathname.indexOf("/estatico/") === 0;
}

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(ESENCIALES); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (claves) {
    return Promise.all(claves.filter(function (k) { return k !== VERSION; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") { return; }
  var url = new URL(req.url);

  if (req.mode === "navigate") {
    // Red siempre; la respuesta NO se guarda. Sin red: la pagina "sin conexion" (cacheada, sin datos).
    e.respondWith(fetch(req).catch(function () {
      return caches.match(SIN_CONEXION);
    }));
    return;
  }

  if (esEstatico(url)) {
    // Stale-while-revalidate: rapido desde cache y se refresca por detras (tras cambiar CSS/JS, la
    // siguiente carga ya trae lo nuevo).
    e.respondWith(caches.open(VERSION).then(function (c) {
      return c.match(req).then(function (guardada) {
        var red = fetch(req).then(function (resp) {
          if (resp && resp.ok && resp.type === "basic") { c.put(req, resp.clone()); }
          return resp;
        }).catch(function () { return guardada; });
        return guardada || red;
      });
    }));
  }
  // Todo lo demas (HTMX, /eventos, POST...) no se toca: va directo a la red, sin cache.
});

// ------------------------------------------------------------------ push
// Solo rutas internas ("/..." pero no "//host" ni con "\"): un payload raro nunca abre una web ajena.
function rutaSegura(r) {
  return (typeof r === "string" && r.charAt(0) === "/" && r.charAt(1) !== "/" && r.indexOf("\\") < 0) ? r : "/";
}

self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = {}; }
  e.waitUntil(self.registration.showNotification(d.titulo || "NEXO", {
    body: d.cuerpo || "",
    tag: d.etiqueta || undefined,
    icon: "/estatico/iconos/nexo-192.png",
    lang: "es",
    data: { ruta: rutaSegura(d.ruta) }
  }));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var ruta = rutaSegura(e.notification.data && e.notification.data.ruta);
  var destino = new URL(ruta, self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (ventanas) {
    for (var i = 0; i < ventanas.length; i++) {
      var v = ventanas[i];
      if (new URL(v.url).origin === self.location.origin && "focus" in v) {
        // navigate() falla si esa ventana no la controla este SW (abierta antes de instalarlo o de
        // una actualizacion): entonces se abre una nueva, para que tocar el aviso lleve SIEMPRE a su pantalla.
        return v.focus().then(function (w) { return (w || v).navigate(destino); })
          .then(function (w) { return w || self.clients.openWindow(destino); })
          .catch(function () { return self.clients.openWindow(destino); });
      }
    }
    return self.clients.openWindow(destino);
  }));
});
