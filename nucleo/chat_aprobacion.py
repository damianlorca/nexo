# -*- coding: utf-8 -*-
"""T1020 (pieza 3): minichat de UNA solicitud de la cola de aprobaciones (boton «Preguntar» de la tarjeta).

- Historial en memoria/chats_aprobaciones/<id>.jsonl (una linea por mensaje: n, cuando, tipo, quien, texto).
- Contexto: SOLO esa solicitud y su ficha (nucleo.guardian.explicacion), pasado por auditor.tapar; si aun asi lleva
  algo privado, solo contesta Qwen local.
- Contesta NVIDIA, el primer modelo vivo de config nvidia.modelos (T1039, como el chat de tareas); de reserva Groq y Gemini API; Qwen local al final.
  Claude solo si Damian pulsa «Escalar» (queda guardada para la proxima sesion de Code; no gasta nada hasta entonces).
- Sin acciones: el chat solo explica. Aprobar o denegar es con los botones de la tarjeta.

CLI (para Claude):
    .venv\\Scripts\\python.exe -m nucleo.chat_aprobacion escalados
    .venv\\Scripts\\python.exe -m nucleo.chat_aprobacion responder A0064 3 "texto"
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime

from nucleo import aprobaciones as ap
from nucleo.candado import bloqueo
from nucleo.config import RAIZ

CARPETA = RAIZ / "memoria" / "chats_aprobaciones"
MAX_MENSAJE = 2000
MAX_PREVIOS = 6
QUIEN = {"damian": "Tú", "nvidia": "NVIDIA", "groq": "Groq", "gemini_api": "Gemini", "qwen": "Qwen (tu PC)",
         "claude": "Claude", "nexo": "NEXO"}


class ChatRechazado(ValueError):
    """Peticion invalida al minichat (id raro, mensaje vacio o demasiado largo, PARADA...)."""


def _id_valido(id_: str) -> str:
    id_ = str(id_ or "").strip().upper()
    if not re.fullmatch(r"A\d{4,6}", id_):
        raise ChatRechazado(f"Solicitud no válida: {id_ or '(vacía)'}.")
    return id_


def _ruta(id_: str):
    return CARPETA / f"{_id_valido(id_)}.jsonl"


def historial(id_: str) -> list[dict]:
    try:
        lineas = _ruta(id_).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    salida = []
    for l in lineas:
        try:
            salida.append(json.loads(l))
        except ValueError:
            continue
    return salida


def conversacion(id_: str) -> list[dict]:
    """Para pintar: con el nombre llano de quien habla."""
    return [{**x, "quien_nombre": QUIEN.get(x.get("quien", ""), x.get("quien", ""))} for x in historial(id_)]


def _anadir(id_: str, **campos) -> dict:
    CARPETA.mkdir(parents=True, exist_ok=True)
    with bloqueo(CARPETA / ".candado_chats.lock"):
        linea = {"n": len(historial(id_)) + 1, "cuando": datetime.now().strftime(ap.FORMATO), **campos}
        with _ruta(id_).open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    return linea


# ------------------------------------------------------------------ contexto y prompt
def contexto(s: dict) -> str:
    """La solicitud y su ficha, nada mas (ni la cola, ni tareas, ni memoria)."""
    from nucleo import auditor, guardian
    ex = guardian.explicacion(s)
    sobre = "; ".join(f"{x['ruta']} ({x['papel']})" for x in ex.get("sobre") or []) or "-"
    trib = s.get("tribunal") or {}
    lineas = [
        f"PETICION: {s.get('accion', '')} (estado: {s.get('estado')}, vence {str(s.get('vence') or '-')[:16]})",
        f"ORDEN EXACTA: {str(s.get('detalle') or '')[:1500]}",
        f"QUE HACE: {ex.get('que')}", f"SOBRE QUE: {sobre}", f"TIPO: {ex.get('tipo_llano')}",
        f"SE PUEDE DESHACER: {ex.get('deshacer')}", f"QUIEN LO PIDE: {ex.get('quien')}",
        f"PARA QUE: {ex.get('para_que')}", f"RIESGO: {ex.get('riesgo')}", f"RECOMENDACION: {ex.get('recomendacion')}",
        f"POR QUE LE LLEGA A DAMIAN: {ex.get('por_que_a_ti') or '-'}",
    ]
    if trib.get("dictamenes"):
        lineas.append("TRIBUNAL: " + "; ".join(f"{d.get('voto')} ({d.get('familia') or d.get('id')}): "
                                               f"{d.get('motivo')}" for d in trib["dictamenes"]))
    return auditor.tapar("\n".join(lineas))


def prompt(s: dict, pregunta: str, previos: list[dict]) -> str:
    from nucleo import auditor
    from nucleo import ahora as reloj
    charla = "\n".join(f"{'Damian' if x.get('quien') == 'damian' else 'Asistente'}: {x.get('texto', '')}"
                       for x in previos[-MAX_PREVIOS:] if x.get("tipo") in ("mensaje", "respuesta"))
    return reloj.con_fecha(auditor.tapar(
        "Eres el asistente que explica a Damian UNA peticion de permiso de su agente personal (NEXO). Contesta en "
        "espanol claro y breve (maximo 120 palabras), sin jerga, usando SOLO la informacion de abajo; si no esta ahi, "
        "dilo. Tu no decides ni haces nada: si Damian quiere aprobar o denegar, que use los botones de la tarjeta.\n\n"
        f"{contexto(s)}\n\n" + (f"CONVERSACION HASTA AHORA:\n{charla}\n\n" if charla else "")
        + f"Pregunta de Damian: {pregunta}\nRespuesta:"))


def proveedores() -> list:
    """NVIDIA (primer vivo de config, T1039), de reserva Groq y Gemini API (Qwen local va aparte, al final)."""
    import proveedores as P
    return [P.NvidiaProvider(modelos=(P.modelo_nvidia_principal(),), timeout=60.0, max_tokens=800),
            P.GroqProvider(rondas=1, timeout=45.0), P.GeminiAPIProvider(rondas=1, timeout=45.0)]


def _qwen():
    import proveedores as P
    return P.QwenProvider()


def _contestar(id_: str, s: dict, msg: dict) -> dict:
    from nucleo import auditor
    texto = prompt(s, msg["texto"], historial(id_)[:-1])
    privado = auditor.motivos_privados(texto)
    fallos = []
    for prov in ([] if privado else proveedores()) + [_qwen()]:
        try:
            if not prov.disponible():
                fallos.append(f"{prov.nombre}: no disponible")
                continue
            r = prov.enviar(texto)
        except Exception as e:   # noqa: BLE001 - se prueba el siguiente
            fallos.append(f"{prov.nombre}: {type(e).__name__}")
            continue
        if r.ok and r.texto.strip():
            extra = {"modelo": getattr(prov, "ultimo_modelo", "") or (r.meta or {}).get("modelo", "")}
            if privado:
                extra["solo_local"] = "; ".join(privado)
            return _anadir(id_, tipo="respuesta", quien=prov.nombre, ref=msg["n"],
                           texto=auditor.tapar(r.texto.strip())[:3000], **extra)
        fallos.append(f"{prov.nombre}: {r.estado}")
    return _anadir(id_, tipo="respuesta", quien="nexo", ref=msg["n"], error=True, fallos=fallos,
                   texto="Ahora mismo no me contesta ninguna IA. Vuelve a intentarlo en un rato o pulsa «Escalar» "
                         "para que lo vea Claude.")


# ------------------------------------------------------------------ API
def _limpio(texto: str) -> str:
    t = str(texto or "").strip()
    if not t:
        raise ChatRechazado("Escribe la pregunta.")
    if len(t) > MAX_MENSAJE:
        raise ChatRechazado(f"La pregunta es muy larga (máximo {MAX_MENSAJE} caracteres).")
    return t


def preguntar(id_: str, texto: str, escalar: bool = False) -> list[dict]:
    """Damian pregunta sobre la solicitud `id_`. Con escalar=True no contesta ninguna IA: queda para Claude.
    Devuelve las lineas nuevas (su mensaje y la respuesta o el aviso de escalado)."""
    from nucleo import parada
    id_ = _id_valido(id_)
    texto = _limpio(texto)
    try:
        s = ap.ver(id_)
    except ap.NoEncontrada:
        raise ChatRechazado(f"No hay ninguna solicitud {id_}.")
    msg = _anadir(id_, tipo="mensaje", quien="damian", texto=texto, escalar=bool(escalar))
    if escalar:
        return [msg, _anadir(id_, tipo="escalado", quien="nexo", ref=msg["n"],
                             texto="Guardada para Claude: la verá en la próxima sesión de Code y contestará aquí. "
                                   "No gasta nada hasta entonces.")]
    if parada.activa():
        return [msg, _anadir(id_, tipo="respuesta", quien="nexo", ref=msg["n"], error=True,
                             texto="NEXO está parado (PARADA): no pregunto a ninguna IA hasta que pulses «Seguir».")]
    return [msg, _contestar(id_, s, msg)]


def escalados() -> list[dict]:
    """Preguntas escaladas a Claude sin contestar, de todos los minichats (las mas antiguas primero)."""
    salida = []
    if not CARPETA.is_dir():
        return salida
    for p in sorted(CARPETA.glob("A*.jsonl")):
        lineas = historial(p.stem)
        contestadas = {x.get("ref") for x in lineas if x.get("tipo") == "respuesta" and x.get("quien") == "claude"}
        mensajes = {x["n"]: x for x in lineas if x.get("tipo") == "mensaje"}
        for x in lineas:
            if x.get("tipo") == "escalado" and x.get("ref") not in contestadas:
                salida.append({"solicitud": p.stem, "n": x.get("ref"), "cuando": x["cuando"],
                               "pregunta": mensajes.get(x.get("ref"), {}).get("texto", "")})
    return sorted(salida, key=lambda e: e["cuando"])


def responder_claude(id_: str, n: int, texto: str) -> dict:
    """Claude contesta (desde una sesion de Code) a la pregunta n escalada en el minichat de `id_`."""
    id_ = _id_valido(id_)
    if not any(x.get("tipo") == "escalado" and x.get("ref") == n for x in historial(id_)):
        raise ChatRechazado(f"No hay pregunta escalada {n} en {id_}.")
    return _anadir(id_, tipo="respuesta", quien="claude", ref=n, texto=_limpio(texto)[:8000])


def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["escalados"]:
        for e in escalados():
            print(f"{e['solicitud']} #{e['n']} ({e['cuando']}): {e['pregunta']}")
        return 0
    if argv[:1] == ["responder"] and len(argv) >= 4 and argv[2].isdigit():
        print(responder_claude(argv[1], int(argv[2]), " ".join(argv[3:])))
        return 0
    print(__doc__.split("CLI (para Claude):")[1])
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
