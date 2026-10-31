# -*- coding: utf-8 -*-
"""Tareas: lista filtrable, ficha, y crear/editar/anotar/completar/verificar llamando a nucleo.tareas.

- Todo pasa por la API del core (anadir, actualizar, anotar, completar, verificar), que ya
  bloquea el almacen entre procesos. Aqui solo se valida lo que llega del formulario.
- Principio de Verdad: verificar exige evidencia escrita; se muestran estado_real y testeado.
- Editar lleva la huella de la tarea que se vio: si NEXO (u otro proceso) cambio la tarea entre
  medias, se rechaza en vez de pisar su cambio sin avisar.
- Errores de validacion: 200 + HX-Retarget al hueco de error de ESE formulario (lo escrito no
  se pierde). Exito: se repinta la ficha entera desde el core (nunca optimista) + aviso.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from interfaz import lecturas, presentar
from interfaz.vistas import pintar, pintar_panel
from nucleo import investigacion, responsables
from nucleo import tarea_v2 as V
from nucleo import tareas as T

router = APIRouter()
log = logging.getLogger("uvicorn.error")

MAX_TITULO = 200
MAX_TEXTO = 8000
MAX_ETIQUETA = 60


class Invalido(Exception):
    pass


# ------------------------------------------------------------------ validacion
def _medida(valor: str, nombre: str) -> int:
    try:
        v = int(valor)
    except (TypeError, ValueError):
        raise Invalido(f"{nombre}: tiene que ser un número del 1 al 5.")
    if not 1 <= v <= 5:
        raise Invalido(f"{nombre}: tiene que ser un número del 1 al 5.")
    return v


def _v2(objetivo, hecho_cuando, donde, tipo, motivo_quien, coste_eur, instrucciones) -> dict:
    """Los campos del formato v2 del formulario (T1010). Los limites del formato se exigen aqui, en la web;
    al guardar el core solo avisa."""
    objetivo = (objetivo or "").strip()
    if len(objetivo) > V.LIM_OBJETIVO:
        raise Invalido(f"El objetivo no puede pasar de {V.LIM_OBJETIVO} caracteres (ahora {len(objetivo)}).")
    hecho = [x.strip() for x in (hecho_cuando or "").splitlines() if x.strip()]
    if len(hecho) > V.MAX_HECHO:
        raise Invalido(f"«Hecho cuando» admite como mucho {V.MAX_HECHO} comprobaciones, una por línea.")
    if tipo and tipo not in V.TIPOS:
        raise Invalido("El tipo no es válido.")
    coste_eur = (coste_eur or "").strip().replace(",", ".")
    try:
        euros = float(coste_eur) if coste_eur else None
    except ValueError:
        raise Invalido("El coste en euros tiene que ser un número (0 si no cuesta).")
    if euros is not None and euros < 0:
        raise Invalido("El coste en euros no puede ser negativo.")
    instrucciones = (instrucciones or "").strip()
    if len(instrucciones) > MAX_TEXTO or len((donde or "")) > 300 or len((motivo_quien or "")) > 200:
        raise Invalido("Alguno de los textos del formato es demasiado largo.")
    return {"objetivo": objetivo, "hecho_cuando": hecho, "donde": (donde or "").strip(),
            "motivo_quien": (motivo_quien or "").strip(), "coste_eur": euros, "instrucciones_damian": instrucciones,
            "tipo": tipo or None}


def _campos(titulo, detalle, importancia, urgencia, dificultad, coste, depende, limite, etiquetas) -> dict:
    titulo = (titulo or "").strip()
    if not titulo:
        raise Invalido("El título no puede estar vacío.")
    if len(titulo) > MAX_TITULO:
        raise Invalido(f"El título no puede pasar de {MAX_TITULO} caracteres.")
    detalle = (detalle or "").strip()
    if len(detalle) > MAX_TEXTO:
        raise Invalido(f"El detalle no puede pasar de {MAX_TEXTO} caracteres.")
    if depende not in T.DEPENDENCIAS:
        raise Invalido("«Depende de» no es válido.")
    limite = (limite or "").strip() or None
    if limite:
        try:
            datetime.strptime(limite, "%Y-%m-%d")
        except ValueError:
            raise Invalido("La fecha límite tiene que ser AAAA-MM-DD.")
    lista = []
    for e in re.split(r"[,\n]", etiquetas or ""):
        e = e.strip()
        if e and e not in lista:
            if len(e) > MAX_ETIQUETA:
                raise Invalido(f"Etiqueta demasiado larga (máximo {MAX_ETIQUETA}): {e[:20]}…")
            lista.append(e)
    # Guardia de responsables (05/10): si Damian se la asigna a si mismo desde la web, es decision suya.
    if depende == "damian" and responsables.motivo({"titulo": titulo, "detalle": detalle, "etiquetas": lista}) is None:
        lista.append(responsables.PREFIJO + "gustos")
    return {"titulo": titulo, "detalle": detalle, "importancia": _medida(importancia, "Importancia"),
            "urgencia": _medida(urgencia, "Urgencia"), "dificultad": _medida(dificultad, "Dificultad"),
            "coste": _medida(coste, "Coste"), "depende": depende, "limite": limite, "etiquetas": lista}


def _rechazo(request: Request, hueco: str, motivo: str):
    resp = pintar(request, "_mensaje_error.html", motivo=motivo)
    resp.headers["HX-Retarget"] = f"#{hueco}"
    resp.headers["HX-Reswap"] = "innerHTML"
    return resp


# ----------------------------------------------------------------------- vistas
def _version(t: dict) -> str:
    """Huella del contenido de la tarea. `actualizada` solo tiene segundos: dos cambios en el
    mismo segundo no se distinguirian; la huella cambia con cualquier campo."""
    return hashlib.sha256(json.dumps(t, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]


def _ficha(t: dict) -> dict:
    # T230: la vista humana (presentar.ficha) + lo crudo de siempre para el "Detalle tecnico"
    # T1010: las notas antiguas (en tareas_detalle/) siguen saliendo en «las notas anteriores»
    antiguas = T.detalle(t["id"]).get("notas_antiguas") or []
    vista_t = {**t, "notas": antiguas + list(t.get("notas") or [])} if antiguas else t
    return {**presentar.ficha(vista_t, T.cargar()["tareas"]), "t": t, "instrucciones": T.instrucciones(t),
            "avisos_formato": V.validar(t) if V.declara_v2(t) else [], "tipos": V.TIPOS, "version": _version(t), "estado_real": T.estado_real(t), "puntuacion": T.puntuacion(t),
            "urgencia_efectiva": T.urgencia_efectiva(t), "dias": T.dias_restantes(t),
            "modelo": T.modelo_sugerido(t), "claude": T.sugerencia_claude(t), "notas": list(reversed(t.get("notas") or [])),
            "estados": T.ESTADOS, "dependencias": T.DEPENDENCIAS, "es_investigacion": investigacion.es_investigacion(t),
            "decisiones": investigacion.DECISIONES, "destino": _destino(t)}


def _destino(t: dict) -> dict | None:
    """T837: quien hara la tarea y, si nadie, por que. Mirarlo nunca rompe la ficha."""
    try:
        from nucleo import enrutado
        return enrutado.destino(t)
    except Exception:
        return None


def _detalle(request: Request, id_tarea: str, aviso: str = ""):
    t = lecturas.tarea(id_tarea)
    if t is None:
        return pintar(request, "_mensaje_error.html", 404, motivo=f"La tarea {id_tarea} no existe.")
    return pintar(request, "_tarea_detalle.html", aviso=aviso, **_ficha(t))


def _lista(**params) -> dict:
    """Lista humana (T230). Los filtros viejos (estado del core, depende, etiqueta, q) siguen valiendo."""
    return presentar.lista(**{k: (v or "") for k, v in params.items()})


PARAMS = ("estado", "depende", "etiqueta", "q", "categoria", "tema", "proveedor", "origen", "orden")


@router.get("/tareas")
def pagina(request: Request, estado: str = "vivas", depende: str = "", etiqueta: str = "", q: str = "",
           categoria: str = "", tema: str = "", proveedor: str = "", origen: str = "", orden: str = "prioridad"):
    params = dict(estado=estado, depende=depende, etiqueta=etiqueta, q=q, categoria=categoria, tema=tema,
                  proveedor=proveedor, origen=origen, orden=orden)
    try:
        lista = _lista(**params)
    except Exception as e:
        log.warning("tareas: lista fallo: %s", type(e).__name__)
        lista = {"error": type(e).__name__, "f": {**{k: "" for k in PARAMS}, "estado": "vivas", "orden": "prioridad"},
                 "grupos": [], "cuenta": {}, "ops": {}, "ordenes": presentar.ORDENES, "quienes": {}}
    return pintar(request, "tareas.html", dependencias=T.DEPENDENCIAS, **lista)


@router.get("/tareas/lista")
def lista(request: Request, estado: str = "vivas", depende: str = "", etiqueta: str = "", q: str = "",
          categoria: str = "", tema: str = "", proveedor: str = "", origen: str = "", orden: str = "prioridad"):
    params = dict(estado=estado, depende=depende, etiqueta=etiqueta, q=q, categoria=categoria, tema=tema,
                  proveedor=proveedor, origen=origen, orden=orden)
    datos = {}

    def leer():
        datos.update(_lista(**params))
        return datos
    resp = pintar_panel(request, "_tareas_lista.html", "/tareas/lista?" + urlencode(params), leer)
    # La barra de direcciones refleja el filtro (recargar o compartir la URL da lo mismo).
    resp.headers["HX-Replace-Url"] = datos.get("url") or "/tareas"
    return resp


@router.post("/tareas")
def crear(request: Request, titulo: str = Form(""), detalle: str = Form(""), importancia: str = Form("3"),
          urgencia: str = Form("3"), dificultad: str = Form("3"), coste: str = Form("2"),
          depende: str = Form("ia"), limite: str = Form(""), etiquetas: str = Form(""), objetivo: str = Form(""),
          hecho_cuando: str = Form(""), donde: str = Form(""), tipo: str = Form(""), motivo_quien: str = Form(""),
          coste_eur: str = Form(""), instrucciones_damian: str = Form("")):
    try:
        campos = _campos(titulo, detalle, importancia, urgencia, dificultad, coste, depende, limite, etiquetas)
        campos.update(_v2(objetivo, hecho_cuando, donde, tipo, motivo_quien, coste_eur, instrucciones_damian))
    except Invalido as e:
        return _rechazo(request, "error-nueva", str(e))
    campos = {k: v for k, v in campos.items() if v not in ("", None, [])}     # lo vacio no se manda
    t = T.anadir(campos.pop("titulo"), **campos)
    return Response(status_code=204, headers={"HX-Redirect": f"/tareas/{t['id']}"})


@router.get("/tareas/{id_tarea}")
def ficha(request: Request, id_tarea: str):
    t = lecturas.tarea(id_tarea)
    if t is None:
        return pintar(request, "error.html", 404, codigo_error=404)
    return pintar(request, "tarea.html", **_ficha(t))


@router.get("/tareas/{id_tarea}/ficha")
def ficha_sola(request: Request, id_tarea: str):
    t = lecturas.tarea(id_tarea)
    if t is None:
        return pintar(request, "_mensaje_error.html", motivo=f"La tarea {id_tarea} ya no existe.")
    return pintar(request, "_tarea_ficha.html", **_ficha(t))


@router.get("/tareas/{id_tarea}/tecnico")
def tecnico(request: Request, id_tarea: str):
    """T230: el "Detalle tecnico" (lo crudo para las IAs), repintado aparte por SSE."""
    t = lecturas.tarea(id_tarea)
    if t is None:
        return pintar(request, "_mensaje_error.html", motivo=f"La tarea {id_tarea} ya no existe.")
    return pintar(request, "_tarea_tecnico.html", **_ficha(t))


@router.post("/tareas/{id_tarea}/nota")
def anotar(request: Request, id_tarea: str, nota: str = Form("")):
    nota = nota.strip()
    if not nota or len(nota) > MAX_TEXTO:
        return _rechazo(request, "error-nota", f"La nota tiene que tener entre 1 y {MAX_TEXTO} caracteres.")
    if T.anotar(id_tarea, nota) is None:
        return _rechazo(request, "error-nota", f"La tarea {id_tarea} no existe.")
    return _detalle(request, id_tarea, "Nota añadida.")


@router.post("/tareas/{id_tarea}/completar")
def completar(request: Request, id_tarea: str, nota: str = Form(""), decision: str = Form(""),
              motivo: str = Form(""), despues: str = Form(""), evidencia: str = Form(""),
              estado_real: str = Form("HECHO SIN TESTEAR")):
    if len(nota) > MAX_TEXTO or len(motivo) > MAX_TEXTO:
        return _rechazo(request, "error-completar", "Nota demasiado larga.")
    actual = lecturas.tarea(id_tarea)
    if actual is not None and investigacion.es_investigacion(actual):
        # T674: una investigacion se cierra con RESULTADO; ADOPTAR/ADAPTAR la deja esperando su integracion
        try:
            r = investigacion.decidir(id_tarea, decision, motivo or nota, quien="damian")
        except (ValueError, T.RevisionPendiente) as e:
            return _rechazo(request, "error-completar", f"No se cierra: {e}.")
        if r["hija"]:
            return _detalle(request, id_tarea, f"Resultado {decision.upper()}: creada la integración {r['hija']['id']}; "
                                               "la investigación se cierra sola cuando se verifique.")
        return _detalle(request, id_tarea, "Investigación cerrada con resultado DESCARTAR (HECHO SIN TESTEAR).")
    try:
        # T1010: cerrar exige decir que sigue (otra tarea o «nada: motivo») y que se comprobo
        cerrada = T.completar(id_tarea, nota.strip(), despues=despues.strip(),
                              cierre={"estado_real": estado_real, "evidencia": evidencia.strip()})
    except T.RevisionPendiente as e:
        # T192: la origen de un borrador solo se cierra con el veredicto de Claude.
        return _rechazo(request, "error-completar", f"No se cierra: {e}.")
    if cerrada is None:
        return _rechazo(request, "error-completar", f"La tarea {id_tarea} no existe.")
    if cerrada.get("testeado"):
        return _detalle(request, id_tarea, "Tarea cerrada como HECHO Y TESTEADO.")
    return _detalle(request, id_tarea, "Tarea cerrada como HECHO SIN TESTEAR: falta verificarla con evidencia.")


@router.post("/tareas/{id_tarea}/verificar")
def verificar(request: Request, id_tarea: str, evidencia: str = Form("")):
    evidencia = evidencia.strip()
    if len(evidencia) < 10:
        # Principio de Verdad: no vale un tick; hay que decir que se probo y que salio.
        return _rechazo(request, "error-verificar",
                        "Escribe la evidencia (qué se probó y qué salida dio), al menos 10 caracteres.")
    if len(evidencia) > MAX_TEXTO:
        return _rechazo(request, "error-verificar", "Evidencia demasiado larga.")
    actual = lecturas.tarea(id_tarea)
    if actual is None:
        return _rechazo(request, "error-verificar", f"La tarea {id_tarea} no existe.")
    if actual["estado"] != "hecha":
        # T.verificar marcaria testeado aunque este pendiente, y al cerrarla despues saldria
        # HECHO Y TESTEADO con una evidencia de ANTES de hacer el trabajo.
        return _rechazo(request, "error-verificar", "Solo se verifica una tarea hecha: ciérrala primero.")
    from nucleo import evidencias
    vale, motivo = evidencias.evaluar(evidencia)
    if not vale and evidencias.VERIFICAR_ESTRICTO:
        # T160: "funciona bien" pasa de 10 caracteres pero no dice que se probo ni que salio.
        return _rechazo(request, "error-verificar", f"No vale como evidencia: {motivo}.")
    t = T.verificar(id_tarea, evidencia)
    if t is None or not t.get("testeado"):
        return _rechazo(request, "error-verificar", "No se pudo verificar: di qué se probó y qué salida dio.")
    return _detalle(request, id_tarea, "Tarea verificada con evidencia.")


@router.post("/tareas/{id_tarea}/aparcar")
def aparcar(request: Request, id_tarea: str, hasta: str = Form("")):
    """T230: sale de pendientes y vuelve sola ese dia (la vigilancia la despierta y avisa por push)."""
    try:
        t = T.aparcar(id_tarea, hasta)
    except T.NoSePuedeAparcar as e:
        return _rechazo(request, "error-aparcar", f"No se ha aparcado: {e}.")
    if t is None:
        return _rechazo(request, "error-aparcar", f"La tarea {id_tarea} no existe.")
    from datetime import date
    return _detalle(request, id_tarea, f"Aparcada hasta el {date.fromisoformat(t['aparcada_hasta']):%d/%m}: "
                                       "ese día vuelve sola y te llega un aviso.")


@router.post("/tareas/{id_tarea}/recuperar")
def recuperar(request: Request, id_tarea: str):
    t = T.recuperar(id_tarea)
    if t is None:
        return _rechazo(request, "error-aparcar", f"La tarea {id_tarea} no existe.")
    return _detalle(request, id_tarea, "Recuperada: vuelve a estar en pendientes.")


@router.post("/tareas/{id_tarea}/editar")
def editar(request: Request, id_tarea: str, visto: str = Form(""), titulo: str = Form(""), detalle: str = Form(""),
           importancia: str = Form("3"), urgencia: str = Form("3"), dificultad: str = Form("3"),
           coste: str = Form("2"), depende: str = Form("ia"), limite: str = Form(""), etiquetas: str = Form(""),
           estado: str = Form(""), bloqueada_por: str = Form(""), objetivo: str = Form(""),
           hecho_cuando: str = Form(""), donde: str = Form(""), tipo: str = Form(""), motivo_quien: str = Form(""),
           coste_eur: str = Form(""), instrucciones_damian: str = Form("")):
    try:
        campos = _campos(titulo, detalle, importancia, urgencia, dificultad, coste, depende, limite, etiquetas)
        campos.update(_v2(objetivo, hecho_cuando, donde, tipo, motivo_quien, coste_eur, instrucciones_damian))
        if campos["instrucciones_damian"] == (T.instrucciones(lecturas.tarea(id_tarea) or {"id": id_tarea}) or ""):
            campos.pop("instrucciones_damian")          # sin cambios: no se reescribe (ni se saca de lo privado)
        if campos["tipo"] is None:
            campos.pop("tipo")
        if estado not in T.ESTADOS:
            raise Invalido("Estado no válido.")
    except Invalido as e:
        return _rechazo(request, "error-editar", str(e))
    actual = lecturas.tarea(id_tarea)
    if actual is None:
        return _rechazo(request, "error-editar", f"La tarea {id_tarea} no existe.")
    if visto != _version(actual):
        return _rechazo(request, "error-editar",
                        f"La tarea cambió mientras la editabas (última vez: {actual.get('actualizada')}). "
                        "Recarga la ficha y vuelve a aplicar tus cambios: no se ha guardado nada.")
    campos.update(estado=estado, bloqueada_por=bloqueada_por.strip()[:MAX_ETIQUETA])
    if actual["estado"] == "hecha" and estado != "hecha":
        # Reabrir no puede dejar la comprobacion vieja puesta: al volver a cerrarla saldria
        # HECHO Y TESTEADO sin evidencia nueva (Principio de Verdad).
        campos["testeado"] = False
    try:
        T.actualizar(id_tarea, **campos)
    except T.RevisionPendiente as e:   # T192 / T674 (investigacion sin RESULTADO)
        return _rechazo(request, "error-editar", f"No se ha guardado: {e}.")
    return _detalle(request, id_tarea, "Cambios guardados.")
