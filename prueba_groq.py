# -*- coding: utf-8 -*-
"""Prueba de GroqProvider (T162) con HTTP simulado. No usa red ni clave real."""
import sys
import types
import proveedores
from nucleo import enfriamiento

fallos = 0
def ok(c, n):
    global fallos
    print(("OK   " if c else "FALLO ") + n)
    if not c: fallos += 1

class _Resp:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._p = payload or {}
    def json(self):
        return self._p

def _prov():
    p = proveedores.GroqProvider(modelos=("m1", "m2"), rondas=1, espera=0)
    p._clave = lambda: "CLAVE_FALSA"   # inyecta clave sin tocar secretos
    return p

def _patch(fn):
    import httpx
    orig = httpx.post
    httpx.post = fn
    return orig, httpx

enfriamiento.limpiar("groq")

# 1. respuesta OK en el primer modelo
def h_ok(url, headers=None, json=None, timeout=None):
    return _Resp(200, {"choices": [{"message": {"content": "hola mundo"}}]})
orig, httpx = _patch(h_ok)
r = _prov().enviar("test")
httpx.post = orig
ok(r.ok and r.texto == "hola mundo", "200 -> OK con texto")

# 2. 401 -> BLOCKED (no insiste)
def h_401(url, headers=None, json=None, timeout=None):
    return _Resp(401)
orig, httpx = _patch(h_401)
r = _prov().enviar("test")
httpx.post = orig
ok(r.estado == "BLOCKED", "401 -> BLOCKED")

# 3. todos 429 -> ERROR y enfriamiento activo
enfriamiento.limpiar("groq")
def h_429(url, headers=None, json=None, timeout=None):
    return _Resp(429)
orig, httpx = _patch(h_429)
r = _prov().enviar("test")
httpx.post = orig
ok(r.estado == "ERROR" and "429" in r.detalle, "todos 429 -> ERROR")
ok(enfriamiento.enfriado("groq") is not None, "429 -> proveedor en enfriamiento")
ok(_prov().disponible() is False, "en enfriamiento -> no disponible")
enfriamiento.limpiar("groq")

# 4. primer modelo 429, segundo OK -> fallback de modelo
llamadas = {"n": 0}
def h_mix(url, headers=None, json=None, timeout=None):
    llamadas["n"] += 1
    if llamadas["n"] == 1:
        return _Resp(429)
    return _Resp(200, {"choices": [{"message": {"content": "ok2"}}]})
orig, httpx = _patch(h_mix)
r = _prov().enviar("test")
httpx.post = orig
ok(r.ok and r.texto == "ok2", "fallback al segundo modelo tras 429")
enfriamiento.limpiar("groq")

# 5. sin clave -> NOT_AVAILABLE
p = proveedores.GroqProvider()
p._clave = lambda: ""
ok(p.enviar("x").estado == "NOT_AVAILABLE", "sin clave -> NOT_AVAILABLE")

print(f"\n{7 - fallos}/7 OK")
sys.exit(1 if fallos else 0)
