# -*- coding: utf-8 -*-
"""Turnos automaticos de NEXO: interruptor general, plantillas y TABLA de turnos (T231, rediseno 28/09).

Distinto de la PARADA de emergencia (nucleo/parada.py): la parada lo corta TODO al momento; esto decide
que turnos hay, cuando arrancan y QUE hacen. Los lanza el planificador de NEXO (nucleo/planificador.py),
que corre dentro de la web; ya no hay una Tarea Programada de Windows por turno (ver planificador.py).

  - Interruptor general: bandera memoria/TURNOS_DESACTIVADOS. Con ella no arranca ningun turno.
  - Tabla (memoria/turnos_config.json, versionada): cada turno con nombre, plantilla, instrucciones
    personalizadas (vacio = el texto de la plantilla), tareas concretas, dias, horas, tope de tareas y de
    minutos, si avisa al terminar y si esta activo.
  - Plantillas: el MODO (que hace) es fijo; su texto por defecto es editable (vale para todos los turnos
    que no traigan instrucciones propias).

Todo turno pasa por nucleo.trabajo (OK absoluto + auditor + circuito T192) y ningun turno escribe codigo.

CLI:  .venv\\Scripts\\python.exe -m nucleo.turnos estado|on|off [motivo]|lista
"""
from __future__ import annotations

import json
import re
import secrets
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BANDERA = RAIZ / "memoria" / "TURNOS_DESACTIVADOS"
CONFIG = RAIZ / "memoria" / "turnos_config.json"

MAX_HORAS = 6                 # horas por turno
MAX_HORAS_TRIBUNAL = 48       # T667: el tribunal no genera nada; Damian 04/10: cada 30 min de 22:00 a 08:00
MAX_TAREAS = 5                # tope de tareas/lotes por turno
MIN_MINUTOS, MAX_MINUTOS, MINUTOS_DEFECTO = 10, 180, 55
MAX_TEXTO = 1500
MAX_NOMBRE = 60
MAX_TURNOS = 30
MAX_APAGAR_BAJO = 999         # T670: umbral de propuestas abiertas por debajo del cual el turno se apaga solo

DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_ID_TAREA = re.compile(r"^T\d{3,}$")

# Plantillas: el MODO (que hace el turno) es fijo; el TEXTO es editable.
#   cola / investigacion / correcciones: trabajan tareas que ya existen; el texto va como
#     "indicaciones del turno" dentro del encargo.
#   revisar_codigo / revisar_archivos / vigia: el turno crea su propia tarea (un lote) y el texto es
#     la instruccion principal. Son de SOLO LECTURA sobre el proyecto (guardia en turno_nexo.py).
PLANTILLAS = {
    "cola": {
        "nombre": "Tareas de la cola por orden",
        "solo_lectura": False,
        "texto": "Haz las tareas de la cola, de la mas importante a la menos. De cada una entrega el resultado "
                 "completo y di como se ha comprobado (que se ejecuto o que fuente se leyo). Lo que no se pueda "
                 "comprobar, marcalo como no comprobado; no lo des por hecho. Si no hay tareas que un turno pueda hacer, "
                 "termina sin hacer nada.",
    },
    "revisar_codigo": {
        "nombre": "Revisar el codigo (sin modificar nada)",
        "solo_lectura": True,
        "texto": "Lee este codigo SIN modificar nada y busca solo fallos reales: errores de logica, casos limite, "
                 "excepciones que se tragan, riesgos de seguridad y comentarios que dicen otra cosa que el codigo. "
                 "De cada hallazgo da: archivo y linea, la linea o lineas exactas, que falla (con un ejemplo de "
                 "entrada que lo provoca) y como comprobarlo. Si no puedes dar el ejemplo, no lo apuntes. Sin "
                 "comentarios de estilo. Si no hay hallazgos verificables, responde 'sin hallazgos'.",
    },
    "revisar_archivos": {
        "nombre": "Revisar archivos y apuntar incoherencias",
        "solo_lectura": True,
        "texto": "Lee estos archivos (documentacion, memoria y configuracion) y apunta solo incoherencias reales: "
                 "datos que se contradicen entre archivos, instrucciones desfasadas, referencias a cosas que ya no "
                 "existen y decisiones que chocan. De cada una da los archivos implicados y la cita exacta de cada "
                 "lado. Si no hay ninguna, responde 'sin hallazgos'; no rellenes.",
    },
    "investigacion": {
        "nombre": "Solo investigacion pendiente",
        "solo_lectura": False,
        "texto": "Haz solo las investigaciones pendientes de la cola, de la mas importante a la menos. Cada dato "
                 "clave con su fuente (URL) y la fecha en que se miro. Termina con una conclusion de una frase y con "
                 "RESULTADO ADOPTAR, ADAPTAR o DESCARTAR y el motivo.",
    },
    "correcciones": {
        "nombre": "Solo correcciones de errores",
        "solo_lectura": False,
        "texto": "Solo errores ya conocidos de la cola. De cada uno: donde esta (archivo y linea), la causa probable, "
                 "la correccion concreta y el test o comando que demuestra que queda arreglado. No apliques nada: la "
                 "aplica Claude tras revisarla. Si no puedes reproducir el error, dilo.",
    },
    "vigia": {
        "nombre": "Vigia de novedades",
        "solo_lectura": True,
        "texto": "De esta lista de novedades (repositorios, modelos y herramientas recien aparecidos) elige como "
                 "mucho 5 que sirvan de verdad a un asistente personal local-first (agentes, memoria, interfaz, "
                 "modelos gratis o locales). De cada una: que es, URL y fecha tal como salen en la lista, y para que "
                 "nos serviria en una frase. No uses nada que no este en la lista. Si ninguna sirve, responde 'ninguna'.",
    },
    # T693 R1: radares (nucleo/radar.py). Lee fuentes fijas con codigo, deduplica y deja tarjetas en su almacen; no
    # crea tareas ni llama a IAs (el freno F0 no lo para). `radar=a,b` en las instrucciones elige radares (si no,
    # todos los activos); los que estan en modo simular solo escriben su almacen sombra y un informe.
    "radar": {
        "nombre": "Radares (fuentes fijas, tarjetas)",
        "solo_lectura": False,
        "texto": "Pasada diaria de los radares activos (radar=vigia,oportunidades para elegir). Solo lee fuentes "
                 "fijas y deja tarjetas; no arranca si ningun radar tiene nada que mirar.",
    },
    # T667: no genera nada (el freno F0 no lo para) y no va por trabajo.ciclo: revisa los borradores con 3 IAs
    # gratuitas de familias distintas (nucleo/tribunal.py). Tareas por turno = expedientes.
    "tribunal": {
        "nombre": "Tribunal de revision (sin Claude)",
        "solo_lectura": False,
        "texto": "Pasa los borradores pendientes por el tribunal (3 IAs gratuitas de familias distintas; apelacion si "
                 "no hay unanimidad; bandeja de Damian si persiste). Sin rafagas y respetando el cupo web. No arranca "
                 "si no hay nada que revisar.",
    },
    # T669 (Damian 04/10): la serie de la fase 2 del piloto la lleva NEXO (nucleo/piloto_serie.py). Unica excepcion a
    # "ningun turno escribe codigo": escribe SOLO en su worktree y fusiona SOLO por la puerta, con veredicto de Claude
    # y OK de Damian. No va por trabajo.ciclo. Como el tribunal, admite muchas horas (cada 60 min de dia).
    # T320 (Damian 11/10): NEXO elige solo los modelos. Una pasada diaria del banco con poca cuota; no genera tareas
    # ni va por trabajo.ciclo. Reasigna cada rol solo con evidencia clara y avisa en el Centro si cambia el mejor.
    "modelos": {
        "nombre": "Banco de modelos (diario)",
        "solo_lectura": False,
        "texto": "Una vez al dia vuelve a medir los mejores modelos gratuitos de cada rol (y alguno nuevo del "
                 "inventario) gastando poca cuota. Cambia memoria/modelos/roles.json solo con evidencia clara y avisa "
                 "en el Centro si cambia el mejor. No arranca si hoy ya se midio.",
    },
    # T1011 fase 1 (Bloque 22, 26/10): Kuzushi observa SIN IA lo que ya registra NEXO y deja hallazgos con evidencia
    # (nucleo/kuzushi.py). Sustituye al turno vigia (T272) y a los de revision de codigo y documentacion (archivados).
    # No va por trabajo.ciclo ni lo para el freno (solo observa; sus tareas si lo respetan).
    "kuzushi": {
        "nombre": "Kuzushi (observa sin IA)",
        "solo_lectura": False,
        "texto": "Una pasada nocturna de Kuzushi sin IA: mira tareas, implementador y puerta, turnos, prompts, "
                 "proveedores, guardian, tests, git, salud y las decisiones automaticas de NEXO, y deja hallazgos con "
                 "su evidencia (primera semana: a la cola de Claude). Como mucho 3 tareas por noche y nunca con el "
                 "freno puesto. No arranca si hoy ya observo.",
    },
    # Damian 11/10: fase 2 superada (4/4); desde entonces es PERMANENTE (piloto_serie, modo `permanente`).
    "implementador": {
        "nombre": "Implementador (permanente)",
        "solo_lectura": False,
        "texto": "Implementador permanente: una accion por tanda sobre las tareas con tests dados (tests:dados) y riesgo "
                 "R0-R2, en su worktree y con la puerta de siempre (R2 = OK de Damian sobre el diff). Nunca R3 ni "
                 "blindados. Lo que espera el OK de Damian no bloquea al resto.",
    },
    # T859 bloque 6 (12/10): reels guardados -> ficha completa. PREPARADO e INACTIVO hasta que Damian lo encienda.
    "reels": {
        "nombre": "Reels guardados (lote nocturno)",
        "solo_lectura": False,
        "texto": "Una noche del lote de reels guardados (como mucho ~30 reels, dentro del tope de minutos): ficha "
                 "completa de cada uno y, segun memoria/perfil_privado/reels/config.json, propuestas por tema (tribunal "
                 "y freno) y tarjeta de huecos para Damian, o solo una muestra para revisarla antes. Reanudable; para si "
                 "hay PARADA, poca RAM, sin presupuesto de Gemini o saturacion seguida. No arranca sin reels pendientes.",
    },
}
PLANTILLA_DEFECTO = "cola"


# ------------------------------------------------------------------ interruptor general
def desactivados() -> str | None:
    """Motivo si los turnos estan desactivados; None si estan activos."""
    if not BANDERA.exists():
        return None
    try:
        return json.loads(BANDERA.read_text(encoding="utf-8")).get("motivo") or "sin motivo"
    except Exception:
        return "turnos desactivados (bandera ilegible)"


def desactivar(motivo: str = "") -> str:
    BANDERA.parent.mkdir(parents=True, exist_ok=True)
    BANDERA.write_text(json.dumps({"motivo": motivo or "desactivados por Damian",
                                   "cuando": datetime.now().isoformat(timespec="seconds")},
                                  ensure_ascii=False), encoding="utf-8")
    return f"Turnos DESACTIVADOS: {motivo or 'desactivados por Damian'}"


def activar() -> str:
    if BANDERA.exists():
        BANDERA.unlink()
    return "Turnos ACTIVADOS: los turnos activos de la tabla se ejecutaran a su hora."


def estado() -> str:
    m = desactivados()
    return f"Turnos DESACTIVADOS ({m})" if m else "Turnos ACTIVADOS"


# ------------------------------------------------------------------ validacion
class ConfigInvalida(ValueError):
    pass


def validar_dias(dias) -> list[str]:
    dias = [d for d in DIAS if d in set(dias or [])]
    if not dias:
        raise ConfigInvalida("elige al menos un dia")
    return dias


def validar_horas(horas, maximo: int = MAX_HORAS) -> list[str]:
    if isinstance(horas, str):
        horas = re.split(r"[\s,;]+", horas)
    horas = sorted({h.strip() for h in (horas or []) if h and h.strip()})
    if not horas:
        raise ConfigInvalida("pon al menos una hora")
    malas = [h for h in horas if not _HORA.match(h)]
    if malas:
        raise ConfigInvalida(f"hora no valida (HH:MM): {', '.join(malas)}")
    if len(horas) > maximo:
        raise ConfigInvalida(f"como mucho {maximo} horas por turno")
    return horas


def validar_tareas(texto_o_lista) -> list[str]:
    ids = texto_o_lista if isinstance(texto_o_lista, list) else re.split(r"[\s,;]+", texto_o_lista or "")
    ids = [i.strip().upper() for i in ids if i.strip()]
    malas = [i for i in ids if not _ID_TAREA.match(i)]
    if malas:
        raise ConfigInvalida(f"id de tarea no valido: {', '.join(malas[:5])} (formato T123)")
    return list(dict.fromkeys(ids))[:20]


def _entero(valor, minimo: int, maximo: int, nombre: str) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ConfigInvalida(f"{nombre} no valido ({minimo}-{maximo})")
    if not minimo <= n <= maximo:
        raise ConfigInvalida(f"{nombre} fuera de rango ({minimo}-{maximo})")
    return n


def _si(valor) -> bool:
    return valor is True or str(valor).lower() in ("1", "si", "sí", "true", "on")


def validar_turno(datos: dict) -> dict:
    """Un turno de la tabla, limpio. Lanza ConfigInvalida con un motivo legible."""
    nombre = " ".join(str(datos.get("nombre") or "").split())[:MAX_NOMBRE]
    if not nombre:
        raise ConfigInvalida("ponle un nombre al turno")
    plantilla = datos.get("plantilla") or PLANTILLA_DEFECTO
    if plantilla not in PLANTILLAS:
        raise ConfigInvalida(f"plantilla desconocida: {plantilla}")
    instrucciones = str(datos.get("instrucciones") or "").strip()
    if len(instrucciones) > MAX_TEXTO:
        raise ConfigInvalida(f"las instrucciones pasan de {MAX_TEXTO} caracteres")
    t = {"id": str(datos.get("id") or "") or nuevo_id(), "nombre": nombre, "plantilla": plantilla,
            "instrucciones": instrucciones, "tareas": validar_tareas(datos.get("tareas") or []),
            "dias": validar_dias(datos.get("dias")),
            "horas": validar_horas(datos.get("horas"), MAX_HORAS_TRIBUNAL if plantilla in ("tribunal", "implementador") else MAX_HORAS),
            "max_tareas": _entero(datos.get("max_tareas", 2), 1, MAX_TAREAS, "tope de tareas"),
            "max_minutos": _entero(datos.get("max_minutos", MINUTOS_DEFECTO), MIN_MINUTOS, MAX_MINUTOS,
                                   "tope de minutos"),
            "avisar": _si(datos.get("avisar", True)), "activo": _si(datos.get("activo", True))}
    # T670 (05/10): turno que se apaga solo (activo=False) cuando las propuestas abiertas bajan de este numero
    apagar_bajo = _entero(datos.get("apagar_bajo") or 0, 0, MAX_APAGAR_BAJO, "umbral de apagado")
    if apagar_bajo:
        t["apagar_bajo"] = apagar_bajo
    return t


def nuevo_id() -> str:
    return "u" + secrets.token_hex(3)


# ------------------------------------------------------------------ configuracion (tabla)
def _migrar(datos: dict) -> list[dict]:
    """Config v1 (una plantilla + un horario aplicado a Windows) -> tabla. Decidido por Damian el 28/09:
    el turno de las 03:30 de siempre y el de las 17:00 que programo, cada uno como una fila."""
    plantilla = datos.get("plantilla") if datos.get("plantilla") in PLANTILLAS else PLANTILLA_DEFECTO
    h = datos.get("horario") or {}
    try:
        dias = validar_dias(h.get("dias"))
    except ConfigInvalida:
        dias = list(DIAS)
    comun = {"plantilla": plantilla, "tareas": datos.get("tareas") or [], "dias": dias,
             "max_tareas": datos.get("max_tareas", 2), "max_minutos": MINUTOS_DEFECTO, "avisar": True, "activo": True}
    filas = [dict(comun, id="noche", nombre="Noche 03:30", horas=["03:30"])]
    for hora in h.get("horas") or []:
        if _HORA.match(str(hora)) and hora != "03:30":
            filas.append(dict(comun, id=f"h{hora.replace(':', '')}", nombre=f"Turno {hora}", horas=[hora]))
    salida = []
    for f in filas:
        try:
            salida.append(validar_turno(f))
        except ConfigInvalida:
            pass
    return salida


def cargar() -> dict:
    """{"turnos": [...], "textos": {...}, "archivados": [...]}. Lo que no se entiende se ignora."""
    try:
        datos = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    if "turnos" in datos and isinstance(datos["turnos"], list):
        filas = []
        for f in datos["turnos"]:
            try:
                filas.append(validar_turno(f) if isinstance(f, dict) else None)
            except ConfigInvalida:
                continue
        filas = [f for f in filas if f]
        migrado = False
    else:
        filas = _migrar(datos) if datos else []
        migrado = bool(datos)
    textos = datos.get("textos") or {}
    return {"version": 2, "turnos": filas,
            "textos": {k: str(v)[:MAX_TEXTO] for k, v in textos.items() if k in PLANTILLAS and str(v).strip()},
            "archivados": [a for a in datos.get("archivados") or [] if isinstance(a, dict)][-50:],
            "migrado": migrado, "actualizada": datos.get("actualizada", "")}


def guardar(cfg: dict) -> dict:
    from nucleo.escritura import escribir_atomico
    # Noche 05/10: un turno que ESTE proceso no entiende (p. ej. plantilla nueva con la web sin reiniciar) no se
    # programa, pero tampoco se borra al guardar: asi se perdio el turno del piloto implpil2 el 05/10 a las 01:10.
    ids = {t["id"] for t in cfg["turnos"]}
    try:
        crudos = json.loads(CONFIG.read_text(encoding="utf-8")).get("turnos") or []
    except (OSError, ValueError, AttributeError):
        crudos = []
    ajenos = []
    for f in crudos:
        if not isinstance(f, dict) or f.get("id") in ids:
            continue
        try:
            validar_turno(f)
        except ConfigInvalida:
            ajenos.append(f)
    limpio = {"version": 2, "turnos": cfg["turnos"] + ajenos, "textos": cfg.get("textos") or {},
              "archivados": cfg.get("archivados") or [], "actualizada": datetime.now().isoformat(timespec="seconds")}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(CONFIG, json.dumps(limpio, ensure_ascii=False, indent=1))
    return cargar()


def buscar(turno_id: str, cfg: dict | None = None) -> dict | None:
    return next((t for t in (cfg or cargar())["turnos"] if t["id"] == turno_id), None)


def guardar_turno(datos: dict) -> dict:
    """Crea (sin id) o sustituye (con id existente) un turno. Devuelve el turno guardado."""
    cfg = cargar()
    t = validar_turno(datos)
    for i, viejo in enumerate(cfg["turnos"]):
        if viejo["id"] == t["id"]:
            if "apagar_bajo" not in datos and viejo.get("apagar_bajo"):   # la web no lo envia: no se pierde
                t["apagar_bajo"] = viejo["apagar_bajo"]
            cfg["turnos"][i] = t
            break
    else:
        if len(cfg["turnos"]) >= MAX_TURNOS:
            raise ConfigInvalida(f"como mucho {MAX_TURNOS} turnos")
        cfg["turnos"].append(t)
    guardar(cfg)
    return t


def duplicar(turno_id: str) -> dict:
    t = buscar(turno_id)
    if not t:
        raise ConfigInvalida("ese turno ya no existe")
    copia = dict(t, id="", nombre=f"{t['nombre']} (copia)"[:MAX_NOMBRE], activo=False)   # nace apagado: no chocar
    return guardar_turno(copia)


def archivar(turno_id: str) -> dict:
    """'Borrar' = sacarlo de la tabla y guardarlo en archivados (regla: no se borra nada)."""
    cfg = cargar()
    t = buscar(turno_id, cfg)
    if not t:
        raise ConfigInvalida("ese turno ya no existe")
    cfg["turnos"] = [x for x in cfg["turnos"] if x["id"] != turno_id]
    cfg["archivados"].append(dict(t, archivado=datetime.now().isoformat(timespec="seconds")))
    guardar(cfg)
    return t


def poner_activo(turno_id: str, activo: bool) -> dict:
    t = buscar(turno_id)
    if not t:
        raise ConfigInvalida("ese turno ya no existe")
    return guardar_turno(dict(t, activo=activo))


# ------------------------------------------------------------------ plantillas
def texto_plantilla(pid: str, cfg: dict | None = None) -> str:
    cfg = cfg or cargar()
    return (cfg["textos"].get(pid) or PLANTILLAS[pid]["texto"]).strip()


def plantillas(cfg: dict | None = None) -> list[dict]:
    cfg = cfg or cargar()
    return [{"id": k, "nombre": v["nombre"], "solo_lectura": v["solo_lectura"], "texto": texto_plantilla(k, cfg),
             "editada": k in cfg["textos"]} for k, v in PLANTILLAS.items()]


def editar_texto(plantilla: str, texto: str) -> dict:
    """Cambia el texto por defecto de una plantilla; vacio = vuelve al de fabrica."""
    if plantilla not in PLANTILLAS:
        raise ConfigInvalida(f"plantilla desconocida: {plantilla}")
    texto = (texto or "").strip()
    if len(texto) > MAX_TEXTO:
        raise ConfigInvalida(f"el texto pasa de {MAX_TEXTO} caracteres")
    cfg = cargar()
    if texto and texto != PLANTILLAS[plantilla]["texto"]:
        cfg["textos"][plantilla] = texto
    else:
        cfg["textos"].pop(plantilla, None)
    return guardar(cfg)


def contexto(turno: dict | None = None, plantilla: str | None = None, manual: bool = False) -> dict:
    """Lo que necesita turno_nexo.py para trabajar: de un turno de la tabla, o de una plantilla suelta (CLI)."""
    cfg = cargar()
    if turno is None:
        pid = plantilla if plantilla in PLANTILLAS else PLANTILLA_DEFECTO
        turno = {"id": "", "nombre": PLANTILLAS[pid]["nombre"], "plantilla": pid, "instrucciones": "", "tareas": [],
                 "max_tareas": 2, "max_minutos": MINUTOS_DEFECTO, "avisar": True}
    pid = turno["plantilla"]
    return {"turno_id": turno["id"], "nombre": turno["nombre"], "plantilla": pid,
            "nombre_plantilla": PLANTILLAS[pid]["nombre"],
            "texto": turno.get("instrucciones") or texto_plantilla(pid, cfg),
            "personalizadas": bool(turno.get("instrucciones")), "solo_lectura": PLANTILLAS[pid]["solo_lectura"],
            "tareas": turno.get("tareas") or [], "max_tareas": turno.get("max_tareas", 2),
            "max_minutos": turno.get("max_minutos", MINUTOS_DEFECTO), "avisar": turno.get("avisar", True),
            "apagar_bajo": turno.get("apagar_bajo") or 0, "manual": manual}


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    args = sys.argv[1:] or ["estado"]
    orden = args[0].lower()
    if orden in ("off", "desactivar", "apagar"):
        print(desactivar(" ".join(args[1:])))
    elif orden in ("on", "activar", "encender"):
        print(activar())
    elif orden == "lista":
        for t in cargar()["turnos"]:
            print(f"{'ON ' if t['activo'] else 'off'} {t['id']}: {t['nombre']} · {t['plantilla']} · "
                  f"{','.join(t['horas'])} · {len(t['dias'])} dias")
    else:
        print(estado())
