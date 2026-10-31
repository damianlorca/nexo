# -*- coding: utf-8 -*-
"""T967 (Damian 17/10): el tribunal juzga los vetos R1 ("implementar Txxx" y "fusionar Txxx") antes de que lleguen a Damian.

Al crearse una R1 (nucleo/riesgo.autorizacion) queda con `tribunal: pendiente`. Aqui, 3 IAs de familias distintas
(las de nucleo.tribunal.TRIBUNAL: API gratuitas primero, web con cupo al final) reciben la tarea, su DONDE y el
contrato de su test en tests_dados/ (si lo hay) y contestan APROBAR o VETAR con su motivo.

    3/3 APROBAR -> R1 aprobada sin Damian (decidida_por = tribunal)
    3/3 VETAR   -> R1 vetada sin Damian (se puede deshacer con "Deshacer veto")
    cualquier otro caso (division, fallo de proveedor, sin cupo) -> bandeja de Damian con los dictamenes, y ahi corre
    el plazo de 8 h (silencio = si).

Solo R1 de tipo veto (Damian 17/10: la misma regla vale para las de fusion). Nunca R2 ni R3 (aprobaciones.solicitar lo impide). Lo llama el turno del tribunal
(nucleo.tribunal.ciclo) y la CLI.

T1020 (18/10): el guardian de aprobaciones (nucleo/guardian.py) reutiliza este tribunal para lo AMBAR reversible
(prompt_aprobacion) y para las R2 con la puerta en verde (prompt_fusion), solo con proveedores API (web=False) y
con el mismo criterio de 3/3. Esas no pasan por pendientes()/ciclo(): las juzga guardian.trabajar.

    .venv\\Scripts\\python.exe -m nucleo.tribunal_r1 ciclo|estado
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from nucleo import aprobaciones as ap
from nucleo import tareas as T

RAIZ = Path(__file__).resolve().parent.parent
LIMITE_CONTRATO = 3500   # caracteres del test dado que van en el prompt
FIN = "FIN_DICTAMEN"
_VOTO = re.compile(r"(?im)^[ \t>*_-]*VOTO[ \t*_]*:[ \t*_]*(APROBAR|VETAR)\b")
_MOTIVO = re.compile(r"(?im)^[ \t>*_-]*MOTIVO[ \t*_]*:[ \t*_]*(.+)$")


def contrato(tarea: dict) -> str:
    """Lo que dicen los tests que Claude dejo para esta tarea (tests_dados/<nombre>), recortado. '' si no hay."""
    from nucleo import riesgo
    trozos = []
    for ruta in riesgo.previsto(tarea).get("rutas", []):
        f = RAIZ / "tests_dados" / Path(ruta).name
        if ruta.startswith("tests/") and f.is_file():
            trozos.append(f"# {f.name}\n" + f.read_text(encoding="utf-8", errors="replace")[:LIMITE_CONTRATO])
    return "\n\n".join(trozos)


def prompt_fusion(tarea: dict, extra: dict) -> str:
    """Prompt de una R1 de FUSION (el codigo ya esta escrito y paso la puerta): ¿se fusiona este diff en principal?"""
    test = contrato(tarea)
    return (
        "Eres revisor independiente de NEXO, el asistente personal local-first de Damian. Un implementador automatico "
        "ya escribio el cambio de abajo en una rama aparte y paso los tests de la puerta. Falta decidir si se fusiona "
        "en la rama principal. Responde APROBAR si el cambio cumple la TAREA, es seguro y de alcance razonable; VETAR "
        "si hace algo distinto de lo pedido, es peligroso, toca lo que no debe o esta claramente mal. Dudas menores no "
        "son motivo de veto.\n\n"
        f"TAREA {tarea.get('id', '')}: {tarea.get('titulo', '')}\n\nDETALLE:\n<<<\n{tarea.get('detalle') or '(sin detalle)'}\n>>>\n\n"
        f"RESUMEN DEL CAMBIO: {extra.get('resumen') or '(sin resumen)'}\n\nDIFF (resumido):\n<<<\n{extra.get('diff_resumido') or '(sin diff)'}\n>>>\n\n"
        + (f"CONTRATO (tests dados):\n<<<\n{test}\n>>>\n\n" if test else "")
        + f"Responde EXACTAMENTE con estas dos lineas y nada despues de {FIN}:\n"
        "VOTO: APROBAR|VETAR\nMOTIVO: una frase\n" + FIN)


def prompt(tarea: dict) -> str:
    detalle = tarea.get("detalle") or "(sin detalle)"
    test = contrato(tarea)
    return (
        "Eres revisor independiente de NEXO, el asistente personal local-first de Damian. Otra IA (el implementador) "
        "va a programar la TAREA de abajo, sola, en una rama aparte, y solo se fusionara si pasa una puerta de tests. "
        "Antes de empezar hay que decidir si merece la pena: ¿esta bien definida, es util, es segura y de alcance "
        "razonable, y encaja con lo que se pide en DONDE? Responde APROBAR si debe implementarse, VETAR si es "
        "erronea, inutil, peligrosa, duplicada o esta mal definida. Dudas menores no son motivo de veto.\n\n"
        f"TAREA {tarea.get('id', '')}: {tarea.get('titulo', '')}\n\nDETALLE (incluye DONDE):\n<<<\n{detalle}\n>>>\n\n"
        + (f"CONTRATO (tests ya escritos que el codigo debe cumplir):\n<<<\n{test}\n>>>\n\n" if test else
           "CONTRATO: no hay tests dados para esta tarea.\n\n")
        + f"Responde EXACTAMENTE con estas dos lineas y nada despues de {FIN}:\n"
        "VOTO: APROBAR|VETAR\nMOTIVO: una frase\n" + FIN)


def prompt_aprobacion(s: dict, ficha: dict) -> str:
    """T1020: prompt de una solicitud AMBAR que el guardian manda al tribunal. Quien llama lo pasa por auditor.tapar."""
    sobre = "; ".join(f"{x['ruta']} ({x['papel']})" for x in ficha.get("sobre") or []) or "-"
    return (
        "Eres revisor independiente de NEXO, el asistente personal local-first de Damian. Un agente de NEXO pide "
        "permiso para hacer la ACCION de abajo en el PC de Damian. Responde APROBAR si es segura, no pierde nada que "
        "no se pueda recuperar y encaja con lo que dice que quiere; VETAR si puede perder contenido de Damian, sacar "
        "datos privados del PC, tocar claves o archivos de control, o no tiene sentido. Dudas menores no son motivo "
        "de veto.\n\n"
        f"ACCION: {s.get('accion', '')}\nORDEN EXACTA:\n<<<\n{str(s.get('detalle') or '')[:1500]}\n>>>\n\n"
        f"QUE HACE (analisis automatico): {ficha.get('que', '')}\nTIPO: {ficha.get('tipo_llano', '')}\n"
        f"SOBRE: {sobre}\n¿SE PUEDE DESHACER?: {ficha.get('deshacer', '')}\n"
        f"PARA QUE (lo que dice quien lo pide): {ficha.get('para_que', '')}\n\n"
        f"Responde EXACTAMENTE con estas dos lineas y nada despues de {FIN}:\n"
        "VOTO: APROBAR|VETAR\nMOTIVO: una frase\n" + FIN)


def parsear(texto: str) -> dict:
    """{'voto': 'APROBAR'|'VETAR'|None, 'motivo': str, 'error': str}. Sin FIN o sin VOTO claro = error (no cuenta)."""
    t = texto or ""
    if FIN not in t:
        return {"voto": None, "motivo": "", "error": "salida truncada (sin FIN_DICTAMEN)"}
    votos = {m.upper() for m in _VOTO.findall(t)}
    if len(votos) != 1:
        return {"voto": None, "motivo": "", "error": "voto ausente o contradictorio"}
    m = _MOTIVO.search(t)
    return {"voto": votos.pop(), "motivo": (m.group(1).strip() if m else "")[:300], "error": ""}


def decidir(dictamenes: list[dict]) -> tuple[str, str]:
    """(resultado, motivo) segun los dictamenes: aprobar / vetar solo con 3/3; si no, bandeja."""
    votos = [d["voto"] for d in dictamenes]
    if len(votos) == 3 and set(votos) == {"APROBAR"}:
        return "aprobar", "tribunal 3/3 APROBAR"
    if len(votos) == 3 and set(votos) == {"VETAR"}:
        return "vetar", "tribunal 3/3 VETAR"
    if len(votos) < 3:
        return "bandeja", f"tribunal sin quorum ({len(votos)}/3 dictamenes validos)"
    return "bandeja", f"tribunal dividido ({votos.count('APROBAR')} APROBAR / {votos.count('VETAR')} VETAR)"


def _reunir(tarea: dict, limite: float | None, texto: str | None = None,
            web: bool = True) -> tuple[list[dict], list[dict]]:
    """Hasta 3 dictamenes validos de familias distintas. Devuelve (dictamenes, fallos). web=False: solo API (T1020)."""
    from nucleo import banco_modelos
    from nucleo import tribunal as TR
    lista = banco_modelos.ordenar("revisar", TR.TRIBUNAL, TR.clave_banco)
    texto, dicts, fallos, fams = texto or prompt(tarea), [], [], set()
    for c in lista:
        if len(dicts) >= 3 or (limite and time.time() > limite):
            break
        if c.familia in fams or (c.web and not web) or not TR._disponible(c) or not TR._esperar(c, limite):
            continue
        try:
            r = TR._proveedor(c).enviar(texto)
            fallo = None if r.ok else f"{r.estado}: {r.detalle}"[:200]
        except Exception as ex:
            r, fallo = None, f"{type(ex).__name__}: {ex}"[:200]
        TR._marcar_uso(c)
        d = parsear(r.texto) if fallo is None else {"error": fallo}
        if d["error"]:
            fallos.append({"id": c.id, "motivo": d["error"]})
            continue
        dicts.append({"id": c.id, "familia": c.familia, "voto": d["voto"], "motivo": d["motivo"],
                      "cuando": ap._txt(ap._ahora())})
        fams.add(c.familia)
    return dicts, fallos


def pendientes() -> list[dict]:
    return [s for s in ap.cargar()["solicitudes"]
            if s["estado"] == "pendiente" and s.get("nivel") == "R1" and s.get("tipo") == "veto"
            and (s.get("tribunal") or {}).get("estado") == "pendiente"]


def juzgar(s: dict, limite: float | None = None) -> dict:
    """Pasa UNA R1 por el tribunal y aplica el resultado en la cola de aprobaciones."""
    id_tarea = (s.get("extra") or {}).get("tarea", "")
    tarea = T.buscar(id_tarea) if id_tarea else None
    if tarea is None:
        dicts = []
        resultado, motivo = "bandeja", f"tribunal: no encuentro la tarea {id_tarea or '?'}"
    else:
        extra = s.get("extra") or {}
        if extra.get("fusion"):
            dicts, fallos = _reunir(tarea, limite, prompt_fusion(tarea, extra))
        else:
            dicts, fallos = _reunir(tarea, limite)
        resultado, motivo = decidir(dicts)
        if fallos and resultado == "bandeja" and len(dicts) < 3:
            motivo += "; fallos: " + ", ".join(f["id"] for f in fallos)
    try:
        return ap.registrar_tribunal(s["id"], resultado, dicts, motivo)
    except ap.EstadoInvalido:
        return ap.ver(s["id"])   # Damian se adelanto o vencio el plazo mientras tanto


def ciclo(limite: float | None = None, max_r1: int = 3) -> dict:
    """Juzga hasta `max_r1` R1 pendientes de tribunal. Devuelve {id: resultado}."""
    ap.caducar()
    hechos = {}
    for s in pendientes()[:max_r1]:
        if limite and time.time() > limite:
            break
        r = juzgar(s, limite)
        hechos[s["id"]] = (r.get("tribunal") or {}).get("resultado") or r["estado"]
    return hechos


def candidatas() -> int:
    return len(pendientes())


def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["ciclo"]:
        print(ciclo())
        return 0
    if argv[:1] == ["estado"]:
        print(f"R1 esperando al tribunal: {[s['id'] for s in pendientes()]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(_cli(sys.argv[1:]))
