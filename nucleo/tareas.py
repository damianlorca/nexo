"""Cola de trabajo de Nexo: una lista con criterio, no una lista a mano.

Por que existe esto
-------------------
Hasta ahora la cola era `memoria/tareas.md`, escrito a mano. Eso tenia
dos problemas: el orden lo decidia quien escribiera esa noche, y nadie
podia preguntarle nada al archivo ("que puedo hacer yo sin Damian",
"que vence esta semana"). Damian lo pidio asi el 11/09/2026: tareas
ordenadas por importancia, urgencia, dificultad, coste y de quien
dependen.

El almacen de verdad es `memoria/tareas.json`. `memoria/tareas.md` se
GENERA a partir de el: es la vista para leer, no la fuente. Si alguien
edita el .md a mano, el siguiente render se lo lleva por delante.

Las cinco medidas
-----------------
- importancia 1-5: cuanto cambia si esto sale bien. No es lo mismo que
  urgencia. La auditoria del codigo era importante y nada urgente.
- urgencia 1-5: cuanto duele el retraso. Si la tarea tiene `limite`,
  la urgencia se CALCULA de los dias que quedan y el valor a mano se
  ignora: una fecha no opina, manda.
- dificultad 1-5: cuanto cuesta hacerlo bien.
- coste 1-5: cuanto gasta (tokens, tiempo de maquina, dinero).
- depende: "ia" lo hago yo solo; "damian" no avanza sin el; "externo"
  espera a un tercero (una convocatoria, un servidor, un plazo); "claude"
  (T674) necesita una sesion de Claude: los turnos de NEXO no la cogen.

La puntuacion
-------------
    puntuacion = (3*urgencia + 2*importancia) / freno
    freno      = 1 + 0.30*(dificultad-1) + 0.20*(coste-1)

La urgencia pesa mas que la importancia porque lo urgente caduca y lo
importante no. Dificultad y coste frenan, no vetan: entre dos tareas
que valen lo mismo, primero la barata. La dificultad frena mas que el
coste a proposito, porque una tarea dificil ademas suele fallar.

`depende` NO entra en la puntuacion. Entra en el reparto: las de
Damian van a su lista y las mias a la mia. Mezclarlas seria lo de
antes, una lista donde lo primero es algo que yo no puedo tocar.

Candado entre procesos
-----------------------
Desde el 11/09 por la tarde, este almacen lo tocan VARIOS PROCESOS a
la vez: un turno de Claude por la CLI, el bot de Telegram (/tarea,
/hecha) y cualquier script suelto. anadir(), actualizar() y anotar()
van envueltos en nucleo.candado.bloqueo() para que dos escrituras a
la vez no se coman los cambios la una de la otra. Ver nucleo/candado.py.

Modelo sugerido (T005)
-----------------------
Damian, 11/09 07:08: "ahora todo va con Opus 5 y concentracion alta,
tambien para cosas que no lo necesitan... que al plantear una tarea
se proponga el modelo optimo". `modelo_sugerido()` calcula eso a ojo
de dificultad e importancia (lo que de verdad pide criterio; urgencia
y coste no entran: la urgencia no exige mas modelo, y el coste ya
frena en la puntuacion). Es solo una SUGERENCIA que se muestra al
crear la tarea y en la vista .md: Nexo no puede cambiar el modelo de
una rutina programada por su cuenta (bloqueado por la plataforma para
rutinas atadas a un dispositivo, ver memoria/estado.json), asi que
quien la aplica es Damian, donde haga falta.

Testeado (22/09/2026)
----------------------
La Constitucion (Principio de Verdad) exige distinguir HECHO Y
TESTEADO de HECHO SIN TESTEAR: que exista el codigo no basta, hace
falta evidencia de que funciona. En vez de anadir mas estados (la
decision de quedarse con 5 y no los 10 de la especificacion maestra
sigue en pie, ver documentacion/I_MANUALES/04_NEXO_TASK_MANAGEMENT.md),
se anade un campo `testeado` (booleano) ORTOGONAL a `estado`. Con eso
el vocabulario de la Constitucion sale de combinar los dos campos, sin
tocar la maquina de estados (ver `estado_real()`):

    pendiente            -> PLANIFICADO
    en_curso             -> EN PROCESO
    bloqueada            -> BLOQUEADO
    hecha + testeado=no  -> HECHO SIN TESTEAR   (valor por defecto)
    hecha + testeado=si  -> HECHO Y TESTEADO

`completar()` NO marca testeado por su cuenta (cerrar una tarea no es
lo mismo que comprobarla). Para eso esta `verificar()`, que ademas
pide dejar constancia de la evidencia (que se probo, que salida dio)
como nota — no un simple tick.

Formato v2 y almacen partido (T1010 paso 2, 17/10)
---------------------------------------------------
Los campos y limites del formato v2 estan en `nucleo/tarea_v2.py`; los archivos (tareas.json solo con las
vivas, tareas_historial.jsonl, tareas_detalle/) en `nucleo/tareas_almacen.py`. Aqui: `anadir`/`actualizar`
aceptan los nombres viejos y los v2 (quien, prioridad, esfuerzo, fecha_limite, depende_de, tipo, origen...),
`cargar()` devuelve TODAS las tareas (vivas e historial) con los dos juegos de campos, y `completar()` exige
`despues` y `cierre` con evidencia. Un almacen con "version": 1 se guarda en el formato viejo.

bloqueada_por / pregunta_id
-----------------------------
Estos dos campos ya existian en el esquema desde antes pero no se
usaban: `bloqueada_por` para enlazar con el id de la tarea que
bloquea a esta, y `pregunta_id` para enlazar con una pregunta enviada
a Damian que hay que resolver antes de seguir. Usarlos en vez de
inventar campos nuevos cuando una tarea depende de otra o de una
respuesta suya.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from nucleo import tarea_v2 as V
from nucleo import tareas_almacen as AL
from nucleo.candado import bloqueo
from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico


ALMACEN = RAIZ / "memoria" / "tareas.json"
VISTA = RAIZ / "memoria" / "tareas.md"
# Copia para leer en Obsidian (Damian 23/09: "lo miro directamente en el vault").
VISTA_VAULT = RAIZ.parent / "contexto" / "proyectos" / "nexo" / "tareas-por-prioridad.md"
CANDADO = RAIZ / "memoria" / ".candado_tareas.lock"

DEPENDENCIAS = ("ia", "damian", "externo", "claude")

# T1010 paso 2: formato de almacen. 1 = el de siempre (todo en tareas.json, campos viejos); 2 = tareas.json
# solo con las no cerradas, historial aparte, detalle aparte y registros compactos v2 (ver nucleo/tarea_v2.py).
# Un almacen que ya existe conserva su version hasta que la migracion (herramientas_nube/migrar_tareas_v2.py)
# la sube; uno nuevo nace en 2.
FORMATO = 2

# Estados vivos (cuentan como trabajo) y cerrados (solo historial).
# "propuesta" (T192, 27/09): la propuso NEXO en un borrador y espera el veredicto de Claude
# (nucleo/revision.py). Nadie la trabaja: siguiente(), trabajo y el router solo cogen pendiente/en_curso.
VIVOS = ("pendiente", "en_curso", "esperando", "bloqueada", "aparcada", "propuesta")
CERRADOS = ("hecha", "descartada")
ESTADOS = VIVOS + CERRADOS

# Dias que quedan -> urgencia. Se lee de arriba abajo y para en el
# primer tope que se cumple. Vencida o para hoy es un 5 sin discusion.
ESCALA_PLAZO = ((3, 5), (7, 4), (21, 3), (60, 2))

# Cada medida con SU valor por defecto. Si llega basura en un campo,
# cae aqui: no a un 3 generico que disfrazaria de normal un dato malo.
DEFECTOS = {
    "importancia": 3,
    "urgencia": 3,
    "dificultad": 3,
    "coste": 2,
}

CAMPOS_NUMERICOS = tuple(DEFECTOS)

# peso = 2*dificultad + importancia -> etiqueta de modelo sugerido.
# La dificultad pesa el doble porque es la que de verdad mide cuanto
# criterio hace falta; la importancia suma pero no basta ella sola
# (una tarea importante y facil no necesita un modelo caro, solo que
# se haga bien y con calma). Techos: minimo 2*1+1=3, maximo 2*5+5=15.
NIVELES_MODELO = (
    (6, "sonnet, concentracion media"),
    (11, "sonnet, concentracion alta"),
    (99, "opus, concentracion alta"),
)

# T005: lo mismo con los nombres que se eligen en la app de escritorio al abrir la sesion
# (selector de modelo y de esfuerzo), para que la cola de la web diga que poner.
MODELO_APP = {
    "sonnet, concentracion media": ("Sonnet", "medium"),
    "sonnet, concentracion alta": ("Sonnet", "high"),
    "opus, concentracion alta": ("Opus", "high"),
}


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hoy() -> date:
    return date.today()


def _recortar(n, por_defecto: int = 3) -> int:
    """Cualquier cosa que no sea un 1-5 se convierte en un 1-5."""

    try:
        v = int(n)
    except (TypeError, ValueError):
        return por_defecto

    return max(1, min(5, v))


def _abool(v) -> bool:
    """Cualquier cosa que no sea claramente verdadera se convierte en False.

    Acepta booleanos, y tambien lo que puede llegar por CLI/Telegram
    como texto: "si"/"true"/"1" cuentan como True, el resto como False.
    """

    if isinstance(v, bool):
        return v

    if isinstance(v, str):
        return v.strip().lower() in ("si", "sí", "true", "1", "yes")

    return bool(v)


def plantilla(titulo: str, **campos) -> dict:
    """Una tarea nueva con todos los campos puestos (los viejos y los v2). Acepta los dos nombres."""

    t = {
        "id": "",
        "titulo": titulo.strip(),
        "detalle": "",
        "importancia": 3,
        "urgencia": 3,
        "dificultad": 3,
        "coste": 2,
        "depende": "ia",
        "estado": "pendiente",
        "limite": None,
        "etiquetas": [],
        "bloqueada_por": "",
        "pregunta_id": "",
        "testeado": False,
        "notas": [],
        "creada": _ahora(),
        "actualizada": _ahora(),
        "cerrada": None,
    }
    t.update(V.vacios())

    campos = dict(campos)
    campos.pop("privado", None)            # lo resuelve anadir() cuando ya hay id
    tipo = campos.pop("tipo", None)
    origen = campos.pop("origen", None)
    campos = V.entrada(campos)

    t.update({k: v for k, v in campos.items() if k in t})
    if "_quien" in campos:
        t["_quien"] = campos["_quien"]

    # T198: desde la CLI las etiquetas llegan como texto "a, b"; se guardan como lista.
    if isinstance(t["etiquetas"], str):
        t["etiquetas"] = [e.strip() for e in t["etiquetas"].split(",") if e.strip()]

    for c, defecto in DEFECTOS.items():
        t[c] = _recortar(t[c], defecto)

    t["testeado"] = _abool(t["testeado"])

    if t["depende"] not in DEPENDENCIAS:
        t["depende"] = "ia"

    if t["estado"] not in ESTADOS:
        t["estado"] = "pendiente"

    _normalizar_v2(t)
    V.aplicar_tipo_origen(t, tipo, origen)
    V.alinear(t)

    return t


def _normalizar_v2(t: dict) -> None:
    """Formas que llegan por CLI/web: hecho_cuando como texto 'a | b', coste_eur como texto, cierre como JSON."""
    hc = t.get("hecho_cuando")
    if isinstance(hc, str):
        t["hecho_cuando"] = [x.strip() for x in re.split(r"\s*\|\s*|\n", hc) if x.strip()]
    elif hc is None:
        t["hecho_cuando"] = []
    ce = t.get("coste_eur")
    if isinstance(ce, str):
        ce = ce.strip().replace(",", ".")
        try:
            t["coste_eur"] = float(ce) if ce else None
        except ValueError:
            t["coste_eur"] = None
    if isinstance(t.get("cierre"), str):
        try:
            t["cierre"] = json.loads(t["cierre"])
        except ValueError:
            t["cierre"] = {}
    if not isinstance(t.get("cierre"), dict):
        t["cierre"] = {}
    for c in ("objetivo", "donde", "despues", "motivo_quien", "instrucciones_damian"):
        t[c] = str(t.get(c) or "").strip()


# --------------------------------------------------------------- disco

def cargar(detalle: bool = False) -> dict:
    """Lee el almacen. Si no existe o esta roto, NO inventa una cola vacia.

    Lo mismo que el hallazgo D1 del estado: una cola en blanco escrita
    encima de la buena es como se pierde el trabajo. Si el archivo
    existe pero no se puede leer, esto revienta a proposito.

    T1010 paso 2: devuelve TODAS las tareas (las vivas de tareas.json y las cerradas del historial), cada
    una abierta a su forma completa en memoria (campos viejos y v2). `detalle=True` ademas trae lo pesado
    (conversaciones, descarte, fallos_turno, notas antiguas) de memoria/tareas_detalle/.
    """

    if not ALMACEN.is_file():
        return {"version": FORMATO, "siguiente_id": 1, "tareas": []}

    datos, historial = AL.leer_coherente(ALMACEN)   # si esta roto, que se entere quien llame

    datos.setdefault("version", 1)
    datos.setdefault("siguiente_id", 1)
    datos.setdefault("tareas", [])
    datos.pop("version_historial", None)

    regs = datos["tareas"]
    if historial:
        por_id = {r["id"]: r for r in regs if isinstance(r, dict) and r.get("id")}
        for r in historial:
            previa = por_id.get(r["id"])
            if previa is None or str(r.get("actualizada") or "") > str(previa.get("actualizada") or ""):
                por_id[r["id"]] = r
        regs = sorted(por_id.values(), key=lambda r: clave_id(r["id"]))

    datos["tareas"] = [V.de_disco(r) for r in regs]

    if detalle and int(datos["version"]) >= 2:
        hay = {p.stem for p in AL.dir_detalle(ALMACEN).glob("*.json")} if AL.dir_detalle(ALMACEN).is_dir() else set()
        for t in datos["tareas"]:
            if t["id"] in hay:
                d = AL.leer_detalle(ALMACEN, t["id"])
                for k in V.DETALLE_CAMPOS:
                    if k in d:
                        t[k] = d[k]
            t["_detalle"] = True

    return datos


def _a_formato_viejo(t: dict) -> dict:
    """Almacen version 1: la tarea tal cual era (campos viejos), sin las vistas v2 que se recalculan al cargar."""
    V.alinear(t)
    r = {k: v for k, v in t.items() if not k.startswith("_")}
    for k in ("prioridad", "esfuerzo", "fecha_limite", "depende_de", "tipo", "origen"):
        r.pop(k, None)
    libre = {k: v for k, v in (t.get("origen") or {}).items() if k not in V._FAMILIA_DE_CLAVE and k != "cat"}
    if libre:
        r["origen"] = libre
    if r.get("quien") == r.get("depende"):
        r.pop("quien", None)
    for k in V.SOLO_V2:
        if r.get(k) in ("", None, [], {}):
            r.pop(k, None)
    return r


def _derramar_detalle(t: dict) -> None:
    """Lo que no es de una tarea viva (notas antiguas, conversaciones, descarte, fallos) se va a su detalle."""
    notas = t.get("notas") or []
    sobran = notas[:-V.MAX_NOTAS] if len(notas) > V.MAX_NOTAS else []
    campos = {k: t[k] for k in V.DETALLE_CAMPOS if k in t}
    hidratada = bool(t.get("_detalle"))
    if sobran:
        t["notas"] = notas[-V.MAX_NOTAS:]
        if hidratada or "notas_antiguas" in campos:
            previas = list(t.get("notas_antiguas") or [])
            vistas = {(n.get("cuando"), n.get("texto")) for n in previas}
            campos["notas_antiguas"] = previas + [n for n in sobran if (n.get("cuando"), n.get("texto")) not in vistas]
        else:
            AL.anadir_notas_antiguas(ALMACEN, t["id"], sobran)
    if hidratada:
        campos.update({k: None for k in V.DETALLE_CAMPOS if k not in t and k not in campos})
    if campos:
        AL.fusionar_detalle(ALMACEN, t["id"], **campos)


def _guardar_v2(datos: dict) -> None:
    vivas, cerradas = [], []
    for t in datos["tareas"]:
        _derramar_detalle(t)
        r = V.a_disco(t)
        if t["estado"] in CERRADOS:
            r["resumen"] = V.resumen(t)
            cerradas.append(r)
        else:
            vivas.append(r)
    cerradas.sort(key=lambda r: clave_id(r["id"]))

    ruta = AL.ruta_historial(ALMACEN)
    version = 0
    viejo = None
    if ruta.is_file():
        version, _ = AL.leer_historial(ALMACEN)
        crudo = ruta.read_text(encoding="utf-8")
        viejo = crudo.split("\n", 1)[1] if "\n" in crudo else ""
    if cerradas or viejo is not None:
        nuevo = AL.texto_historial(0, cerradas).split("\n", 1)[1]
        if nuevo != viejo:
            version += 1
            AL.escribir_historial(ALMACEN, version, cerradas)   # PRIMERO el historial, DESPUES tareas.json

    cuerpo = {"version": 2, "siguiente_id": datos["siguiente_id"], "version_historial": version}
    cuerpo.update({k: v for k, v in datos.items() if k not in ("version", "siguiente_id", "tareas", "version_historial")})
    cuerpo["tareas"] = vivas
    escribir_atomico(ALMACEN, json.dumps(cuerpo, ensure_ascii=False, indent=1) + "\n")


def guardar(datos: dict) -> Path:
    """Guarda el almacen y regenera la vista de leer."""

    if int(datos.get("version", 1) or 1) >= 2:
        _guardar_v2(datos)
    else:
        cuerpo = {k: v for k, v in datos.items() if k != "tareas"}
        cuerpo["tareas"] = [_a_formato_viejo(t) for t in datos["tareas"]]
        escribir_atomico(ALMACEN, json.dumps(cuerpo, ensure_ascii=False, indent=2) + "\n")

    vista = render_md(datos)
    escribir_atomico(VISTA, vista)

    if VISTA_VAULT.parent.is_dir():
        try:
            escribir_atomico(VISTA_VAULT, vista)
        except Exception:
            pass  # el vault es comodidad; la cola de verdad ya esta guardada

    return ALMACEN


# ------------------------------------------------------------- calculo

def dias_restantes(tarea: dict, hoy: date | None = None) -> int | None:
    if not tarea.get("limite"):
        return None

    try:
        limite = datetime.strptime(str(tarea["limite"]), "%Y-%m-%d").date()
    except ValueError:
        return None

    return (limite - (hoy or _hoy())).days


def urgencia_efectiva(tarea: dict, hoy: date | None = None) -> int:
    """La fecha manda sobre el numero puesto a mano."""

    dias = dias_restantes(tarea, hoy)

    if dias is None:
        return _recortar(
            tarea.get("urgencia", DEFECTOS["urgencia"]), DEFECTOS["urgencia"]
        )

    for tope, valor in ESCALA_PLAZO:
        if dias <= tope:
            return valor

    return 1


def puntuacion(tarea: dict, hoy: date | None = None) -> float:
    def medida(nombre: str) -> int:
        defecto = DEFECTOS[nombre]

        return _recortar(tarea.get(nombre, defecto), defecto)

    valor = 3 * urgencia_efectiva(tarea, hoy) + 2 * medida("importancia")

    freno = (
        1
        + 0.30 * (medida("dificultad") - 1)
        + 0.20 * (medida("coste") - 1)
    )

    return round(valor / freno, 2)


def modelo_sugerido(tarea: dict) -> str:
    """Que modelo/nivel pide esta tarea, a ojo de dificultad e importancia.

    Es una SUGERENCIA, no una orden: Nexo no puede cambiar el modelo
    de una rutina programada por su cuenta (bloqueado por la
    plataforma para rutinas atadas a un dispositivo). Sirve para que
    Damian vea de un vistazo si una tarea concreta de verdad necesita
    Opus o le sobra con Sonnet, que era justo su queja del 11/09
    (T005): todo iba con Opus y concentracion alta aunque no hiciera
    falta.
    """

    dificultad = _recortar(
        tarea.get("dificultad", DEFECTOS["dificultad"]), DEFECTOS["dificultad"]
    )
    importancia = _recortar(
        tarea.get("importancia", DEFECTOS["importancia"]), DEFECTOS["importancia"]
    )

    peso = 2 * dificultad + importancia

    for tope, etiqueta in NIVELES_MODELO:
        if peso <= tope:
            return etiqueta

    return NIVELES_MODELO[-1][1]


def sugerencia_claude(tarea: dict) -> dict | None:
    """T005: modelo y esfuerzo para abrir la sesion de Claude Code que trabaje esta tarea.

    None si la tarea no la trabaja la IA (depende de Damian o de terceros): ahi no hay sesion que abrir.
    """
    if tarea.get("depende", "ia") not in ("ia", "claude"):
        return None
    modelo, esfuerzo = MODELO_APP[modelo_sugerido(tarea)]
    return {"modelo": modelo, "esfuerzo": esfuerzo, "texto": f"{modelo} · {esfuerzo}"}


def estado_real(t: dict) -> str:
    """Traduce estado + testeado al vocabulario de la Constitucion.

    HECHO Y TESTEADO / HECHO SIN TESTEAR / EN PROCESO / PLANIFICADO /
    BLOQUEADO son las 5 etiquetas del Principio de Verdad. No son un
    estado nuevo: salen de combinar `estado` (que sigue con sus 5
    valores vivos + 2 cerrados de siempre) con `testeado`.
    """

    if t["estado"] == "hecha":
        return "HECHO Y TESTEADO" if t.get("testeado") else "HECHO SIN TESTEAR"

    return {
        "pendiente": "PLANIFICADO",
        "en_curso": "EN PROCESO",
        "bloqueada": "BLOQUEADO",
        "propuesta": "PROPUESTA (sin revisar)",
    }.get(t["estado"], t["estado"].upper())


def clave_id(tid: str) -> tuple[int, str]:
    """T710: orden NUMERICO de ids ('T999' < 'T1000'); como texto 'T1000' iria antes que 'T200'."""
    m = re.fullmatch(r"T(\d+)", tid or "")
    return (int(m.group(1)), "") if m else (10 ** 12, tid or "")


def ordenadas(tareas: list[dict], hoy: date | None = None) -> list[dict]:
    """De mas a menos puntuacion. Empate: primero la que tiene fecha."""

    def clave(t: dict):
        dias = dias_restantes(t, hoy)

        return (-puntuacion(t, hoy), 999999 if dias is None else dias, clave_id(t["id"]))

    return sorted(tareas, key=clave)


# --------------------------------------------------------------- acciones

def _guardia_responsables(t: dict) -> None:
    """05/10 (Damian): a Damian solo le queda lo que de verdad es suyo; lo demas pasa a Claude con nota."""
    from nucleo import responsables
    nota = responsables.corregir(t)
    if nota:
        t.setdefault("notas", []).append({"cuando": _ahora(), "texto": nota})
    V.alinear(t)


def instrucciones(t: dict) -> str:
    """El texto literal de `instrucciones_damian`; si es privado, lo lee de memoria/perfil_privado/tareas/."""
    v = str(t.get("instrucciones_damian") or "")
    if v.startswith(V.MARCA_PRIVADO):
        try:
            return AL.ruta_privada(ALMACEN, t["id"]).read_text(encoding="utf-8")
        except OSError:
            return ""
    return v


def _fijar_instrucciones(t: dict, texto, privado: bool = False) -> None:
    """Pone las instrucciones de Damian. Privadas (tipo personal o privado=True): al archivo privado y la tarea
    guarda solo la referencia."""
    texto = str(texto or "").strip()
    if not texto:
        t["instrucciones_damian"] = ""
        return
    if privado or t.get("tipo") == "personal":
        ruta = AL.ruta_privada(ALMACEN, t["id"])
        ruta.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(ruta, texto + "\n")
        t["instrucciones_damian"] = V.PRIVADO_REF.format(id=t["id"])
    else:
        t["instrucciones_damian"] = texto


def avisos_formato(tareas: list[dict] | None = None) -> list[tuple[str, list[str]]]:
    """(id, problemas) de las tareas VIVAS que declaran formato v2 y no lo cumplen. Las viejas no cuentan."""
    tareas = cargar()["tareas"] if tareas is None else tareas
    salida = []
    for t in tareas:
        if t.get("estado") in VIVOS and V.declara_v2(t):
            p = V.validar(t)
            if p:
                salida.append((t["id"], p))
    return salida


def _avisar_formato(t: dict) -> None:
    """Los avisos de formato van al Centro (un aviso por tarea y hora) y NUNCA bloquean."""
    try:
        if not V.declara_v2(t):
            return
        problemas = V.validar(t)
        if not problemas:
            return
        from nucleo import avisos
        avisos.emitir("formato", f"{t['id']}: formato de tarea", "; ".join(problemas), ruta=f"/tareas/{t['id']}",
                      clave=f"formato:{t['id']}", urgencia="low")
    except Exception:
        pass


def anadir(titulo: str, **campos) -> dict:
    privado = bool(campos.get("privado"))
    with bloqueo(CANDADO):
        datos = cargar()

        t = plantilla(titulo, **campos)
        t["id"] = "T{:03d}".format(datos["siguiente_id"])
        _guardia_responsables(t)
        if t.get("instrucciones_damian"):
            _fijar_instrucciones(t, t["instrucciones_damian"], privado)
        V.alinear(t)

        datos["siguiente_id"] += 1
        datos["tareas"].append(t)

        guardar(datos)

    _avisar_formato(t)
    return t


def buscar(id_o_texto: str) -> dict | None:
    datos = cargar()

    aguja = id_o_texto.strip().lower()

    for t in datos["tareas"]:
        if t["id"].lower() == aguja:
            return t

    for t in datos["tareas"]:
        if aguja in t["titulo"].lower():
            return t

    return None


def _detalle_de(datos: dict, t: dict) -> dict:
    """El detalle de la tarea (conversaciones, descarte, fallos_turno...): en su archivo (v2) o dentro de ella (v1)."""
    if int(datos.get("version", 1) or 1) >= 2:
        return AL.leer_detalle(ALMACEN, t["id"])
    return {k: t[k] for k in V.DETALLE_CAMPOS if k in t}


def _fijar_detalle(datos: dict, t: dict, **campos) -> None:
    """Escribe campos del detalle de la tarea. Un valor None lo quita."""
    if int(datos.get("version", 1) or 1) >= 2:
        AL.fusionar_detalle(ALMACEN, t["id"], **campos)
        return
    for k, v in campos.items():
        if v is None:
            t.pop(k, None)
        else:
            t[k] = v


def detalle(tarea_id: str) -> dict:
    """Lo pesado de una tarea (notas_antiguas, conversaciones, descarte, fallos_turno). {} si no hay o no existe."""
    datos = cargar()
    t = next((x for x in datos["tareas"] if x["id"].lower() == tarea_id.strip().lower()), None)
    return dict(_detalle_de(datos, t)) if t else {}


def actualizar(tarea_id: str, **campos) -> dict | None:
    # T688 pieza 4: descartar una propuesta exige motivo= y causa= (no son campos de la tarea: se guardan en "descarte")
    motivo_descarte = campos.pop("motivo", None)
    causa_descarte = campos.pop("causa", None)
    # T1010: nombres v2 (quien, prioridad, esfuerzo, fecha_limite, depende_de) -> los viejos; tipo y origen aparte
    privado = bool(campos.pop("privado", False))
    tipo = campos.pop("tipo", None)
    origen = campos.pop("origen", None)
    campos = V.entrada(campos)
    with bloqueo(CANDADO):
        datos = cargar()

        for t in datos["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue

            antes = t["estado"]

            # T674: una investigacion solo se cierra con RESULTADO (y, si se adopta, con la integracion verificada)
            nuevo = campos.get("estado", antes)
            if nuevo in CERRADOS and antes not in CERRADOS:
                from nucleo import investigacion
                motivo = investigacion.motivo_bloqueo(t, nuevo, datos["tareas"])
                if motivo:
                    raise ResultadoPendiente(motivo)
                motivo = motivo_cierre_propuesta(t, nuevo, motivo_descarte, causa_descarte)
                if motivo:
                    raise CierrePropuesta(motivo)
                if nuevo == "descartada" and ET_PROPUESTA in (t.get("etiquetas") or []):
                    _fijar_detalle(datos, t, descarte={"causa": causa_descarte,
                                                       "motivo": " ".join(str(motivo_descarte).split()),
                                                       "cuando": _ahora()})

            for k, v in campos.items():
                if k in t and k not in ("id", "creada"):
                    t[k] = v
            if "_quien" in campos:
                t["_quien"] = campos["_quien"]
            if tipo is not None or origen is not None:
                V.aplicar_tipo_origen(t, tipo, origen)
            _normalizar_v2(t)
            V.alinear(t)
            if "instrucciones_damian" in campos:
                _fijar_instrucciones(t, campos["instrucciones_damian"], privado)

            if t["estado"] != "aparcada":
                t.pop("aparcada_hasta", None)          # T230: la fecha de vuelta solo vale aparcada
                t.pop("estado_antes_de_aparcar", None)

            if antes == "bloqueada" and t["estado"] in ("pendiente", "en_curso"):
                if "fallos_turno" in _detalle_de(datos, t):
                    _fijar_detalle(datos, t, fallos_turno=None)  # T156: reabierta a mano, se le da otra oportunidad

            for c, defecto in DEFECTOS.items():
                t[c] = _recortar(t[c], defecto)

            t["testeado"] = _abool(t.get("testeado", False))
            V.alinear(t)

            if t["estado"] not in CERRADOS and {"depende", "etiquetas", "titulo", "detalle", "_quien",
                                                 "motivo_quien"} & set(campos):
                _guardia_responsables(t)

            t["actualizada"] = _ahora()

            if t["estado"] in CERRADOS and not t["cerrada"]:
                t["cerrada"] = _ahora()

            if t["estado"] not in CERRADOS:
                t["cerrada"] = None

            guardar(datos)

            break
        else:
            return None

    if antes != "descartada" and t["estado"] == "descartada" and "cat:integracion" in (t.get("etiquetas") or []):
        from nucleo import investigacion   # T674: sin integracion, la investigacion vuelve a decidirse
        investigacion.hija_descartada(t)

    _avisar_formato(t)
    return t


def anotar(tarea_id: str, nota: str) -> dict | None:
    with bloqueo(CANDADO):
        datos = cargar()

        for t in datos["tareas"]:
            if t["id"].lower() == tarea_id.strip().lower():
                t.setdefault("notas", []).append(
                    {"cuando": _ahora(), "texto": nota.strip()}
                )
                t["actualizada"] = _ahora()

                guardar(datos)

                return t

        return None


def quitar_nota(tarea_id: str, cuando: str, texto: str) -> dict | None:
    """T290: deshace una nota puesta desde el chat de la tarea. Quita SOLO la que coincide
    exactamente (fecha y texto); si ya no esta, devuelve None y no toca nada."""
    with bloqueo(CANDADO):
        datos = cargar()
        for t in datos["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue
            notas = t.get("notas") or []
            for i in range(len(notas) - 1, -1, -1):
                if notas[i].get("cuando") == cuando and notas[i].get("texto") == texto:
                    del notas[i]
                    t["actualizada"] = _ahora()
                    guardar(datos)
                    return t
            return None
        return None


def fijar_resumen_humano(tarea_id: str, texto: str) -> dict | None:
    """T230/T290: resumen de 1-2 frases para Damian, en su propio campo (nunca pisa el detalle).
    Texto vacio lo quita (vuelve el provisional sacado del detalle)."""
    with bloqueo(CANDADO):
        datos = cargar()
        for t in datos["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue
            if texto.strip():
                t["resumen_humano"] = texto.strip()
            else:
                t.pop("resumen_humano", None)
            t["actualizada"] = _ahora()
            guardar(datos)
            return t
        return None



# ----------------------------------------------------------- aparcar (T230)
# Damian 28/09: "Aparcar hasta..." sale de pendientes y vuelve SOLA ese dia (con aviso push:
# lo emite quien llama a despertar_aparcadas, la vigilancia de la web). Al volver recupera el
# estado que tenia (una bloqueada vuelve bloqueada), o pendiente si no se sabe.
VUELVEN_A = ("pendiente", "en_curso", "esperando", "bloqueada", "propuesta")


class NoSePuedeAparcar(ValueError):
    pass


def _fecha_aparcar(hasta, hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    try:
        dia = hasta if isinstance(hasta, date) else date.fromisoformat(str(hasta).strip())
    except ValueError:
        raise NoSePuedeAparcar("la fecha tiene que ser AAAA-MM-DD")
    if dia <= hoy:
        raise NoSePuedeAparcar("la fecha de vuelta tiene que ser a partir de mañana")
    if dia > hoy + timedelta(days=366 * 2):
        raise NoSePuedeAparcar("como mucho dos años")
    return dia.isoformat()


def aparcar(tarea_id: str, hasta, nota: str = "", hoy: date | None = None) -> dict | None:
    """Aparca la tarea hasta `hasta` (date o AAAA-MM-DD, a partir de manana). None si no existe.
    NoSePuedeAparcar si la fecha no vale o la tarea esta cerrada."""
    dia = _fecha_aparcar(hasta, hoy)
    with bloqueo(CANDADO):
        datos = cargar()
        for t in datos["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue
            if t["estado"] in CERRADOS:
                raise NoSePuedeAparcar("una tarea cerrada no se aparca")
            if t["estado"] != "aparcada":
                t["estado_antes_de_aparcar"] = t["estado"]
            t["estado"] = "aparcada"
            t["aparcada_hasta"] = dia
            texto = f"Aparcada hasta el {date.fromisoformat(dia):%d/%m/%Y}: vuelve sola ese dia."
            t.setdefault("notas", []).append({"cuando": _ahora(), "texto": texto + (f" {nota.strip()}" if nota.strip() else "")})
            t["actualizada"] = _ahora()
            guardar(datos)
            return t
        return None


def _desaparcar(t: dict, texto: str) -> None:
    antes = t.pop("estado_antes_de_aparcar", None)
    t["estado"] = antes if antes in VUELVEN_A else "pendiente"
    t.pop("aparcada_hasta", None)
    t.setdefault("notas", []).append({"cuando": _ahora(), "texto": texto})
    t["actualizada"] = _ahora()


def recuperar(tarea_id: str, texto: str = "Recuperada a mano antes de su fecha.") -> dict | None:
    """Saca una tarea aparcada ya. None si no existe; si no esta aparcada, la devuelve sin tocarla."""
    with bloqueo(CANDADO):
        datos = cargar()
        for t in datos["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue
            if t["estado"] == "aparcada":
                _desaparcar(t, texto)
                guardar(datos)
            return t
        return None


def despertar_aparcadas(hoy: date | None = None) -> list[dict]:
    """Devuelve a su estado las aparcadas cuya fecha ya ha llegado. Las aparcadas sin fecha
    (las de antes de T230) no se tocan. Devuelve las que han vuelto."""
    hoy = (hoy or date.today()).isoformat()
    with bloqueo(CANDADO):
        datos = cargar()
        vueltas = []
        for t in datos["tareas"]:
            hasta = t.get("aparcada_hasta")
            if t["estado"] == "aparcada" and hasta and str(hasta) <= hoy:
                _desaparcar(t, f"Ha vuelto sola: estaba aparcada hasta el {hasta}.")
                vueltas.append(t)
        if vueltas:
            guardar(datos)
        return vueltas


MAX_FALLOS_TURNO = 3


def fallo_turno(tarea_id: str, motivo: str, maximo: int = MAX_FALLOS_TURNO) -> dict | None:
    """T156: un fallo mas del turno de NEXO con esta tarea. Al llegar a `maximo` seguidos la bloquea,
    para que el turno deje de reintentarla cada noche (y de generar revisiones para Claude).
    Reabrirla a mano (estado pendiente/en_curso) pone el contador a cero."""
    with bloqueo(CANDADO):
        datos = cargar()

        for t in datos["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue

            n = int(_detalle_de(datos, t).get("fallos_turno") or 0) + 1
            _fijar_detalle(datos, t, fallos_turno=n)
            t["fallos_turno"] = n         # en la copia que se devuelve; el dato vive en el detalle
            texto = f"Turno de NEXO: fallo {n}/{maximo} seguido ({motivo.strip()[:300]})."

            if n >= maximo and t["estado"] in ("pendiente", "en_curso"):
                t["estado"] = "bloqueada"
                t["bloqueada_por"] = (f"T156: {n} fallos seguidos del turno de NEXO (ultimo: {motivo.strip()[:200]}). "
                                      "Reabrirla a mano pone el contador a cero.")
                texto += " Bloqueada."

            t.setdefault("notas", []).append({"cuando": _ahora(), "texto": texto})
            t["actualizada"] = _ahora()
            guardar(datos)

            return t

        return None


def exito_turno(tarea_id: str) -> None:
    """T156: el turno sí sacó algo de esta tarea: los fallos dejan de ser seguidos."""
    with bloqueo(CANDADO):
        datos = cargar()

        for t in datos["tareas"]:
            if t["id"].lower() == tarea_id.strip().lower() and "fallos_turno" in _detalle_de(datos, t):
                _fijar_detalle(datos, t, fallos_turno=None)
                guardar(datos)

                return


def conversacion(tarea_id: str, clave: str) -> dict | None:
    """La conversacion web guardada para esta tarea y `clave` ('chatgpt:autor', 'gemini:revisor'...).

    T183 (Damian 27/09): una conversacion por tarea y tema, iterando en ella hasta una respuesta
    excelente; su URL se guarda en la tarea para retomarla. None si no hay.
    """
    datos = cargar()
    t = next((x for x in datos["tareas"] if x["id"].lower() == tarea_id.strip().lower()), None)
    if t is None:
        return None
    c = (_detalle_de(datos, t).get("conversaciones") or {}).get(clave)
    return dict(c) if isinstance(c, dict) else None


def fijar_conversacion(tarea_id: str, clave: str, **datos) -> dict | None:
    """Guarda/actualiza la conversacion `clave` de la tarea (url, tema, estado, motivo...)."""
    with bloqueo(CANDADO):
        datos_t = cargar()
        for t in datos_t["tareas"]:
            if t["id"].lower() != tarea_id.strip().lower():
                continue
            convs = dict(_detalle_de(datos_t, t).get("conversaciones") or {})
            actual = convs.get(clave) if isinstance(convs.get(clave), dict) else {}
            if datos.get("url") and datos.get("url") != actual.get("url"):
                actual = {"desde": _ahora(), "usos": 0}
            actual.update({k: v for k, v in datos.items() if v is not None})
            actual["usos"] = int(actual.get("usos", 0)) + (1 if datos.get("url") else 0)
            actual["actualizada"] = _ahora()
            convs[clave] = actual
            _fijar_detalle(datos_t, t, conversaciones=convs)
            t["actualizada"] = _ahora()
            guardar(datos_t)
            return dict(actual)
        return None


class RevisionPendiente(ValueError):
    """T192: la tarea espera el veredicto de Claude sobre su borrador; no se cierra antes."""


class CierrePropuesta(RevisionPendiente):
    """T688 pieza 4: una propuesta no se descarta sin motivo y causa, ni se cierra hecha sin haberla aprobado.
    Hereda de RevisionPendiente para que la web, el chat y el bot, que ya la capturan, la traten igual."""


ET_PROPUESTA = "cat:propuesta"
# idea/superado: la idea no vale o ya esta hecha; borrador: se tiro el borrador, la idea no se juzgo (T687)
CAUSAS_DESCARTE = ("idea", "borrador", "superado", "sustituida", "fundida", "archivada", "duplicada")
MIN_MOTIVO_DESCARTE = 15


def motivo_cierre_propuesta(t: dict, nuevo: str, motivo: str | None, causa: str | None) -> str:
    """'' si se puede cerrar; si no, por que no. Solo mira propuestas (cat:propuesta) que se cierran ahora."""
    if ET_PROPUESTA not in (t.get("etiquetas") or []) or t.get("estado") in CERRADOS:
        return ""
    if nuevo == "descartada":
        if causa not in CAUSAS_DESCARTE:
            return (f"{t['id']} es una propuesta: descartarla exige causa ({', '.join(CAUSAS_DESCARTE)}), para "
                    "distinguir una idea mala de un borrador malo")
        if len(" ".join(str(motivo or "").split())) < MIN_MOTIVO_DESCARTE:
            return (f"{t['id']} es una propuesta: descartarla exige un motivo de verdad (minimo "
                    f"{MIN_MOTIVO_DESCARTE} caracteres)")
    if nuevo == "hecha" and t.get("estado") == "propuesta":
        return (f"{t['id']} es una propuesta sin aprobar: no se cierra hecha. Primero el veredicto (tribunal, Claude o "
                "Damian) la aprueba y la convierte en tarea de implementacion, que se cierra y se verifica")
    return ""


class ResultadoPendiente(RevisionPendiente):
    """T674: una investigacion sin RESULTADO (o con ADOPTAR/ADAPTAR y la integracion sin verificar) no se cierra.
    Hereda de RevisionPendiente para que la web, el chat y el bot, que ya la capturan, la traten igual."""


class CierreIncompleto(RevisionPendiente):
    """T1010: una tarea no se cierra sin `despues` (la siguiente o 'nada: motivo') ni `cierre` con evidencia.
    Hereda de RevisionPendiente para que la web, el chat y el bot, que ya la capturan, la traten igual."""


def cierre_ok(estado_real: str = "HECHO SIN TESTEAR", evidencia: str = "", extras: dict | None = None) -> dict:
    """`extras`: los opcionales para Damian (T230 Centro v2) `para_damian` (frase llana) y `novedad` (bool)."""
    return {**extras_cierre(extras), "estado_real": estado_real, "evidencia": evidencia}


EXTRAS_CIERRE = ("para_damian", "novedad")


def extras_cierre(cierre: dict | None) -> dict:
    """Solo `cierre.para_damian` (texto, <=200) y `cierre.novedad` (bool), si vienen y valen; lo demas se ignora."""
    c = cierre if isinstance(cierre, dict) else {}
    salida: dict = {}
    frase = " ".join(str(c.get("para_damian") or "").split())[:200]
    if frase:
        salida["para_damian"] = frase
    if c.get("novedad") is True:
        salida["novedad"] = True
    return salida


def motivo_cierre_incompleto(despues, cierre) -> str:
    """'' si `despues` y `cierre` bastan para cerrar como hecha; si no, que falta."""
    falta = []
    if isinstance(despues, dict):
        if not str(despues.get("titulo") or "").strip():
            falta.append("despues={...} necesita al menos un titulo")
    elif not V.despues_valido(despues):
        falta.append("despues: una tarea siguiente (T###) o 'nada: <motivo de verdad>'")
    c = cierre if isinstance(cierre, dict) else {}
    if c.get("estado_real") not in V.CIERRES:
        falta.append(f"cierre.estado_real: {' o '.join(V.CIERRES)}")
    if len(str(c.get("evidencia") or "").strip()) < V.MIN_EVIDENCIA:
        falta.append(f"cierre.evidencia: que se hizo y que se comprobo (minimo {V.MIN_EVIDENCIA} caracteres)")
    return "; ".join(falta)


def completar(tarea_id: str, nota: str = "", despues=None, cierre: dict | None = None) -> dict | None:
    """Cierra la tarea como hecha. NO la marca testeada por su cuenta:

    cerrar no es lo mismo que comprobar (Principio de Verdad). Queda
    como HECHO SIN TESTEAR hasta que se llame a verificar().

    T192: si la tarea espera la revision de Claude de un borrador
    (etiqueta revision_claude:Txxx) lanza RevisionPendiente. Se cierra
    con el veredicto (python -m nucleo.revision veredicto ...).

    T1010: exige `despues` (la tarea siguiente: su id, o un dict con su contenido para crearla ahora, o
    'nada: motivo') y `cierre` ({"estado_real": "HECHO Y TESTEADO"|"HECHO SIN TESTEAR", "evidencia": ".."}).
    Sin ellos lanza CierreIncompleto y no cierra nada. Con estado_real HECHO Y TESTEADO se llama ademas a
    verificar() con esa evidencia; si la evidencia no vale, queda HECHO SIN TESTEAR y el cierre lo dice.

    T230 (Centro v2): `cierre` admite ademas, OPCIONALES, `para_damian` (una frase llana de que cambia para Damian,
    la que sale en "Hecho desde tu ultima visita") y `novedad` (True si ya puede probarlo). Sin ellas el Centro
    genera la frase con Qwen local o usa el titulo; las llamadas viejas siguen valiendo.
    """

    t = buscar(tarea_id)

    if t is None or t["id"].lower() != tarea_id.strip().lower():
        return None

    espera = next((e.split(":", 1)[1] for e in t.get("etiquetas") or []
                   if e.startswith("revision_claude:")), "")

    if espera:
        raise RevisionPendiente(
            f"{t['id']} espera la revision de Claude ({espera}): se cierra con el "
            "veredicto (python -m nucleo.revision veredicto <borrador> ...)"
        )

    falta = motivo_cierre_incompleto(despues, cierre)
    if falta:
        raise CierreIncompleto(f"{t['id']} no se cierra sin dejar claro como acaba: {falta}")

    if nota:
        anotar(tarea_id, nota)

    pedido = cierre["estado_real"]
    evidencia = " ".join(str(cierre["evidencia"]).split())
    siguiente = "(se crea al cerrar)" if isinstance(despues, dict) else str(despues).strip()

    cerrada = actualizar(tarea_id, estado="hecha", despues=siguiente,
                         cierre=cierre_ok("HECHO SIN TESTEAR", evidencia, cierre))
    if cerrada is None:
        return None

    if isinstance(despues, dict):
        campos = {k: v for k, v in despues.items() if k != "titulo"}
        campos.setdefault("origen", {"prov": "nexo", "tarea_origen": cerrada["id"]})
        nueva = anadir(str(despues["titulo"]), **campos)
        cerrada = actualizar(tarea_id, despues=nueva["id"]) or cerrada

    if pedido == "HECHO Y TESTEADO":
        cerrada = verificar(tarea_id, evidencia) or cerrada

    return cerrada


def verificar(tarea_id: str, evidencia: str = "", registrada: bool = False) -> dict | None:
    """Marca una tarea HECHA como comprobada de verdad.

    `evidencia` es lo que se probo de verdad (un test ejecutado, una
    salida real, un archivo comprobado a mano) y queda anotado en la
    tarea — no es un tick sin mas. No cambia `estado`; si la tarea no
    estaba "hecha" queda testeada igualmente, pero lo normal es
    llamarla despues de completar().

    T160: la evidencia se guarda tambien en memoria/evidencias.jsonl
    (nucleo.evidencias). SIN evidencia no se marca nada: la tarea se
    devuelve tal cual (testeado sigue en False). `registrada=True`
    lo usa nucleo.evidencias.cerrar(), que ya la registro antes.
    """

    if not registrada:
        from nucleo import evidencias

        t = buscar(tarea_id)

        if t is None or t["id"].lower() != tarea_id.strip().lower():
            return None

        try:
            evidencias.registrar(
                t["id"], evidencia, fuente="tareas.verificar",
                debil=not evidencias.VERIFICAR_ESTRICTO,
            )
        except evidencias.EvidenciaInvalida:
            return t

    anotar(tarea_id, f"[verificado] {evidencia}")

    t = actualizar(tarea_id, testeado=True)

    if t is not None and t["estado"] == "hecha":     # T1010: el cierre dice la verdad
        t = actualizar(tarea_id, cierre=cierre_ok("HECHO Y TESTEADO", " ".join(str(evidencia).split()),
                                                  t.get("cierre"))) or t        # conserva para_damian/novedad

    if t is not None and "cat:integracion" in (t.get("etiquetas") or []):
        from nucleo import investigacion   # T674: la integracion verificada cierra su investigacion
        investigacion.hija_verificada(t)

    return t


def listar(
    estado: str | None = None,
    depende: str | None = None,
    vivos: bool = True,
) -> list[dict]:
    datos = cargar()

    fuera = datos["tareas"]

    if vivos and not estado:
        fuera = [t for t in fuera if t["estado"] in VIVOS]

    if estado:
        fuera = [t for t in fuera if t["estado"] == estado]

    if depende:
        fuera = [t for t in fuera if t["depende"] == depende]

    return ordenadas(fuera)


def es_personal(t: dict) -> bool:
    """Tarea de la vida de Damian (becas, contenido personal...): nunca sale hacia una IA externa."""
    return "cat:personal" in (t.get("etiquetas") or [])


ABIERTAS = ("pendiente", "en_curso", "aparcada", "bloqueada", "esperando")


def lista_para_ia_externa(estados: tuple = ABIERTAS, ancho_detalle: int = 160) -> list[str]:
    """T232: una linea por tarea para pasarsela a otra IA (material:interno), SIN las cat:personal.

    Los datos privados que se cuelen en titulo o detalle (rutas del PC, correos, claves) se tapan con
    [privado]: el auditor los bloquearia y la lista entera no saldria.
    """
    from nucleo import auditor

    tapar = auditor.tapar   # la ruta del usuario primero y despues PRIVADO (al reves se filtraba el nombre de usuario)

    lineas = []
    for t in ordenadas([t for t in cargar()["tareas"] if t.get("estado") in estados and not es_personal(t)]):
        et = [e for e in (t.get("etiquetas") or []) if e.startswith(("cat:", "tema:"))]
        det = " ".join(str(t.get("detalle") or "").split())[:ancho_detalle]
        lineas.append(tapar(f"{t['id']} | {t['titulo'][:90]} | imp {t.get('importancia')} urg {t.get('urgencia')} | "
                            f"{t.get('estado')} | {' '.join(et)} | {det}"))
    return lineas


def esta_bloqueada(t: dict, vivas: set[str] | None = None) -> bool:
    """T064: `bloqueada_por` nombra una tarea (T###) que sigue viva. El texto libre o un id que ya no existe o ya
    esta cerrada no bloquean (el texto libre no se puede comprobar; la bloqueante cerrada ya no bloquea)."""
    ids = re.findall(r"\bT\d{3,}\b", t.get("bloqueada_por") or "")
    if not ids:
        return False
    if vivas is None:
        vivas = {x["id"] for x in cargar()["tareas"] if x.get("estado") in VIVOS}
    return any(i in vivas and i != t.get("id") for i in ids)


def siguiente() -> dict | None:
    """Lo siguiente que PUEDO hacer yo sin molestar a nadie (sin las bloqueadas por otra tarea viva, T064)."""

    vivas = {x["id"] for x in cargar()["tareas"] if x.get("estado") in VIVOS}
    candidatas = [
        t
        for t in listar(depende="ia")
        if t["estado"] in ("pendiente", "en_curso") and not esta_bloqueada(t, vivas)
    ]

    return candidatas[0] if candidatas else None


# ----------------------------------------------------------- vista .md

def _sello_plazo(t: dict, hoy: date | None = None) -> str:
    dias = dias_restantes(t, hoy)

    if dias is None:
        return ""

    if dias < 0:
        return f"  **VENCIDA hace {abs(dias)} d** ({t['limite']})"

    if dias == 0:
        return f"  **VENCE HOY** ({t['limite']})"

    return f"  **quedan {dias} d** ({t['limite']})"


def _linea(t: dict, hoy: date | None = None) -> str:
    if t["estado"] == "hecha":
        marca = "[x]" if t.get("testeado") else "[x?]"
    else:
        marca = {
            "pendiente": "[ ]",
            "en_curso": "[~]",
            "esperando": "[?]",
            "bloqueada": "[!]",
            "aparcada": "[-]",
            "propuesta": "[p]",
            "descartada": "[/]",
        }.get(t["estado"], "[ ]")

    cabeza = (
        f"- {marca} **{t['id']} · {t['titulo']}**"
        f"  _(p {puntuacion(t, hoy)})_"
        f"{_sello_plazo(t, hoy)}"
    )

    medidas = (
        f"  - imp {t['importancia']} · urg {urgencia_efectiva(t, hoy)}"
        f" · dif {t['dificultad']} · coste {t['coste']}"
        f" · depende de {t['depende']}"
        f" · modelo sugerido: {modelo_sugerido(t)}"
    )

    trozos = [cabeza, medidas]

    if t["estado"] == "hecha":
        trozos.append(
            f"  - {estado_real(t)}"
            + ("" if t.get("testeado") else " (falta comprobar de verdad)")
        )

    # T1010: lo esencial del formato v2, si la tarea lo trae (las viejas no lo tienen y se ven igual que antes)
    if t.get("objetivo"):
        trozos.append(f"  - objetivo: {t['objetivo']}")
    for comprobacion in t.get("hecho_cuando") or []:
        trozos.append(f"  - hecho cuando: {comprobacion}")
    if t.get("donde"):
        trozos.append(f"  - donde: {t['donde']}")
    if t.get("estado") in CERRADOS and t.get("despues"):
        trozos.append(f"  - despues: {t['despues']}")

    if t.get("bloqueada_por"):
        trozos.append(f"  - BLOQUEADA POR: {t['bloqueada_por']}")

    if t.get("pregunta_id"):
        trozos.append(f"  - pregunta enviada: `{t['pregunta_id']}`")

    if t.get("detalle"):
        for linea in t["detalle"].strip().splitlines():
            trozos.append(f"  - {linea.strip()}" if linea.strip() else "")

    for n in t.get("notas", [])[-3:]:
        trozos.append(f"  - _{n['cuando'][:16]}_ — {n['texto']}")

    return "\n".join(trozos)


def _bloque(titulo: str, tareas: list[dict], vacio: str, hoy=None) -> str:
    cuerpo = (
        "\n\n".join(_linea(t, hoy) for t in tareas) if tareas else f"_{vacio}_"
    )

    return f"## {titulo}\n\n{cuerpo}\n"


def render_md(datos: dict | None = None, hoy: date | None = None) -> str:
    datos = datos or cargar()
    hoy = hoy or _hoy()

    todas = datos["tareas"]

    vivas = [t for t in todas if t["estado"] in VIVOS]

    de_damian = ordenadas(
        [t for t in vivas if t["depende"] == "damian"], hoy
    )
    propuestas = ordenadas([t for t in vivas if t["estado"] == "propuesta"], hoy)
    de_ia = ordenadas(
        [t for t in vivas if t["depende"] == "ia" and t["estado"] != "propuesta"], hoy
    )
    de_fuera = ordenadas([t for t in vivas if t["depende"] == "externo"], hoy)
    de_claude = ordenadas([t for t in vivas if t["depende"] == "claude" and t["estado"] != "propuesta"], hoy)

    hechas = sorted(
        [t for t in todas if t["estado"] in CERRADOS],
        key=lambda t: t.get("cerrada") or "",
        reverse=True,
    )

    sin_testear = [
        t for t in todas if t["estado"] == "hecha" and not t.get("testeado")
    ]

    cabecera = (
        "# Cola de trabajo de Nexo\n\n"
        f"_Generado el {_ahora()}. **No editar a mano**: esta vista sale de "
        "`memoria/tareas.json` y se reescribe sola. Para cambiar algo, "
        "`.venv\\Scripts\\python.exe -m nucleo.tareas` (ver el final)._\n\n"
        f"**{len(de_damian)}** esperan por ti · **{len(de_ia)}** las llevo yo"
        f" · **{len(de_fuera)}** dependen de terceros · "
        f"**{len(hechas)}** cerradas"
        f" ({len(sin_testear)} hechas sin testear todavia).\n\n"
        "Puntuacion `p` = (3·urgencia + 2·importancia) / freno, donde el "
        "freno lo ponen dificultad y coste. Si hay fecha limite, la "
        "urgencia la manda la fecha, no el numero escrito a mano. "
        "'modelo sugerido' es una idea a ojo de dificultad+importancia, "
        "no algo que Nexo aplique solo (ver T005). `[x]` = hecha y "
        "testeada de verdad, `[x?]` = hecha pero sin comprobar todavia "
        "(Principio de Verdad).\n\n"
        "---\n"
    )

    partes = [
        cabecera,
        _bloque(
            "Te toca a ti (sin esto no avanzo)",
            de_damian,
            "Nada pendiente por tu parte. Raro y bueno.",
            hoy,
        ),
        _bloque(
            "Me toca a mi",
            de_ia,
            "Cola vacia. Pideme algo.",
            hoy,
        ),
        _bloque(
            "Propuestas de NEXO (esperan la revision de Claude, no se implementan)",
            propuestas,
            "Ninguna propuesta pendiente.",
            hoy,
        ),
        _bloque(
            "Necesita a Claude (los turnos de NEXO no la cogen)",
            de_claude,
            "Nada esperando a Claude.",
            hoy,
        ),
        _bloque(
            "Depende de terceros",
            de_fuera,
            "Nada esperando fuera.",
            hoy,
        ),
        _bloque(
            "Cerradas",
            hechas[:25],
            "Todavia nada.",
            hoy,
        ),
        (
            "---\n\n"
            "## Como se toca esto\n\n"
            "```\n"
            ".venv\\Scripts\\python.exe -m nucleo.tareas lista\n"
            ".venv\\Scripts\\python.exe -m nucleo.tareas mias\n"
            ".venv\\Scripts\\python.exe -m nucleo.tareas tuyas\n"
            ".venv\\Scripts\\python.exe -m nucleo.tareas siguiente\n"
            '.venv\\Scripts\\python.exe -m nucleo.tareas anadir "Titulo" '
            "--importancia 4 --urgencia 5 --dificultad 2 --coste 1 "
            "--depende damian --limite 2026-09-22\n"
            ".venv\\Scripts\\python.exe -m nucleo.tareas hecha T007 "
            '"como quedo" --despues "nada: motivo" --evidencia "que se comprobo"\n'
            ".venv\\Scripts\\python.exe -m nucleo.tareas testeada T007 "
            '"evidencia: comando X ejecutado, salida Y"\n'
            ".venv\\Scripts\\python.exe -m nucleo.tareas estado T007 "
            "bloqueada\n"
            '.venv\\Scripts\\python.exe -m nucleo.tareas nota T007 "lo que sea"'
            "\n```\n"
        ),
    ]

    return "\n".join(partes)


# ----------------------------------------------------------------- cli

def _imprimir(tareas: list[dict]) -> None:
    if not tareas:
        print("(nada)")

        return

    for t in tareas:
        plazo = _sello_plazo(t).replace("**", "").strip()

        print(
            f"{t['id']}  p={puntuacion(t):5.2f}  {t['estado']:10s} "
            f"{t['depende']:7s} {t['titulo']}"
            + (f"  [{plazo}]" if plazo else "")
        )


def _cli(argv: list[str]) -> int:
    if not argv:
        argv = ["lista"]

    accion = argv[0].lower()
    resto = argv[1:]

    if accion in ("lista", "todo"):
        _imprimir(listar())

    elif accion == "mias":
        _imprimir(listar(depende="ia"))

    elif accion == "tuyas":
        _imprimir(listar(depende="damian"))

    elif accion == "siguiente":
        t = siguiente()

        if t is None:
            print("(nada que pueda hacer yo)")
        else:
            sug = sugerencia_claude(t)
            print(f"{t['id']}  {t['titulo']}" + (f"  [abrir con {sug['modelo']}, esfuerzo {sug['esfuerzo']}]" if sug else ""))

    elif accion == "anadir":
        if not resto:
            print("falta el titulo")

            return 2

        titulo = resto[0]
        campos: dict = {}

        i = 1

        while i < len(resto) - 1:
            if resto[i].startswith("--"):
                campos[resto[i][2:]] = resto[i + 1]
                i += 2
            else:
                i += 1

        t = anadir(titulo, **campos)

        print(
            f"anadida {t['id']}  p={puntuacion(t)}  "
            f"modelo sugerido: {modelo_sugerido(t)}"
        )

    elif accion in ("hecha", "completar"):
        # T1010: hecha <id> ["nota"] --despues "T123 | nada: motivo" --evidencia "que se comprobo" [--testeada]
        if not resto:
            print('uso: hecha <id> ["nota"] --despues "T123|nada: motivo" --evidencia "..." [--testeada]')

            return 2

        nota, flags, i = "", {}, 1

        while i < len(resto):
            if resto[i].startswith("--"):
                flags[resto[i][2:]] = resto[i + 1] if i + 1 < len(resto) and not resto[i + 1].startswith("--") else ""
                i += 2 if flags[resto[i][2:]] != "" else 1
            else:
                nota = resto[i]
                i += 1

        try:
            t = completar(resto[0], nota, despues=flags.get("despues"),
                          cierre={"estado_real": "HECHO Y TESTEADO" if "testeada" in flags else "HECHO SIN TESTEAR",
                                  "evidencia": flags.get("evidencia", "")})
        except RevisionPendiente as e:
            print(f"NO cerrada: {e}")

            return 2


        print(f"cerrada {t['id']} (sin testear todavia)" if t else "no encontrada")

    elif accion in ("testeada", "testeado", "verificar", "verificada"):
        t = verificar(resto[0], resto[1] if len(resto) > 1 else "")

        if t is None:
            print("no encontrada")
        elif t.get("testeado"):
            print(f"{t['id']} -> HECHO Y TESTEADO")
        else:
            print(f"{t['id']} NO verificada: falta la evidencia (que se probo y que salio)")

            return 2

    elif accion == "estado":
        # T198: con un solo argumento se caia (IndexError) y un estado inventado se guardaba tal cual.
        if len(resto) < 2 or resto[1] not in ESTADOS:
            print(f"uso: estado <id> <{'|'.join(ESTADOS)}>")

            return 2

        t = actualizar(resto[0], estado=resto[1])

        print(f"{t['id']} -> {t['estado']}" if t else "no encontrada")

    elif accion == "nota":
        t = anotar(resto[0], " ".join(resto[1:]))

        print(f"anotada en {t['id']}" if t else "no encontrada")

    elif accion == "render":
        guardar(cargar())

        print(f"regenerado {VISTA}")

    else:
        print(__doc__)

        return 2

    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    raise SystemExit(_cli(sys.argv[1:]))
