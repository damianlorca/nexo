# -*- coding: utf-8 -*-
"""Puerta de fusion del implementador (T669, F3; plan §5.3). La que de verdad protege `principal`.

En orden, sobre la rama impl/Txxx que dejo nucleo/implementador.py:
  1. Suite completa en verde (otra vez, independiente del implementador) y, en codigo, tests nuevos que fallaban
     antes del cambio (lo comprobo el implementador en el paso 1 y queda en su informe).
  2. Revision del diff por un modelo de OTRA familia que el implementador, con lista fija (¿hace lo pedido?, ¿toca
     algo fuera de alcance?, ¿riesgos?). Usa los revisores de API del tribunal (nunca la web).
  3. Auditor sin IA: archivos privados, R3 (blindados, secretos, borrados, red nueva, dinero), dependencias (version
     fija) y valores inseguros. Lo de los valores inseguros y la cadena de suministro es lo que se adapta de T226
     (trailofbits insecure-defaults / supply-chain-risk-auditor), en codigo: sus plugins solo corren en Claude Code.
  4. Matriz de riesgo sobre el diff REAL (nucleo.riesgo.fusion): R0/R1 dentro de lo aprobado entra; R2 o subida
     de nivel espera el OK de Damian atado al sha del diff; R3 nunca.
  5. Piloto: nada entra sin el FUSIONAR de Claude.
  6. Solo con el arbol de principal limpio (sin cambios sin commit): si no, espera a la siguiente tanda.
     Fusion --no-ff con marca "Implementador: Txxx" (se deshace de una vez).
  7. Salud despues: suite en principal + /salud de la web si esta en marcha. Si falla, marcha atras automatica
     (git revert -m 1), aviso push y la tarea vuelve con el error.

Bloque 21 (25/10): una suite que no da resultado (otra suite de NEXO con el cerrojo, o pasada de tiempo) es fallo de
infraestructura (implementador.FalloInfra), nunca un rojo: en la rama, la tarea espera a la siguiente tanda
(`espera_suite`); en la salud, se repite una vez y solo se deshace la fusion con un rojo de verdad.
"""
from __future__ import annotations

import re
from pathlib import Path

from nucleo import hechos
from nucleo import implementador as I
from nucleo import linea_base
from nucleo import riesgo
from nucleo import tareas as T

# T226 adaptado: valores por defecto inseguros (solo en lineas anadidas de codigo).
INSEGUROS = (
    (re.compile(r"shell\s*=\s*True"), "subprocess con shell=True"),
    (re.compile(r"verify\s*=\s*False"), "TLS sin verificar (verify=False)"),
    (re.compile(r"(?<![\w.])eval\s*\("), "eval() sobre datos"),
    (re.compile(r"(?<![\w.])exec\s*\("), "exec() sobre datos"),
    (re.compile(r"\bpickle\.loads?\s*\("), "pickle.load(s) de datos no fiables"),
    (re.compile(r"\byaml\.load\s*\((?![^)]*SafeLoader)"), "yaml.load sin SafeLoader"),
    (re.compile(r"0\.0\.0\.0"), "escucha en 0.0.0.0 (toda la red)"),
    (re.compile(r"\b0o?777\b"), "permisos 777"),
    (re.compile(r"debug\s*=\s*True"), "modo debug activado"),
    (re.compile(r"_create_unverified_context|CERT_NONE"), "TLS sin verificar"),
    (re.compile(r"\btempfile\.mktemp\s*\("), "tempfile.mktemp (carrera)"),
)
# Damian 04/10: hasta que la revision compruebe hechos contra el repo, la documentacion solo entra con el FUSIONAR de
# Claude (que si los comprueba). En el piloto, ningun revisor de la puerta detecto datos inventados (coincidencia 30 %).
DOCUMENTACION_SIN_CLAUDE = False
_CODIGO = re.compile(r"\.(py|js|mjs|ts|ps1|bat|cmd|sh)$")
_REQ = re.compile(r"(^|/)requirements[^/]*\.txt$")

LISTA_REVISION = (
    "1. ¿Hace lo que pide la tarea, ni mas ni menos?",
    "2. ¿Toca algo fuera de alcance (archivos o cambios que la tarea no pide)?",
    "3. ¿Introduce riesgos (seguridad, datos, red, dependencias, comportamiento que puede romper)?",
)


# Bloque 18 (24/10): el revisor rechazo T939 por `from nucleo import ayuda` ("importacion que probablemente no exista"),
# que es justo lo que exige tests/test_ayuda_entradas.py. Lo que la puerta exige no puede ser motivo de rechazo.
CONTRATOS_NEXO = (
    "- `nucleo` es el paquete principal de este repo (nucleo/ayuda.py, nucleo/tareas.py...): importarlo NO es un riesgo.",
    # Bloque 23 (29/10, K0027): "su ausencia si es motivo de RECHAZAR" se leyo como "todo .py debe tener __main__" y
    # se rechazo T854 (nucleo/silencio.py, un modulo sin __main__, que es lo correcto).
    "- Un modulo SIN bloque `if __name__ == \"__main__\":` es correcto: no hace falta anadirlo. SOLO si el diff tiene "
    "ese bloque, debe empezar por `from nucleo import ayuda; ayuda.atender(__doc__)` (o usar argparse) para que "
    "--help/-h nunca ejecute nada (lo comprueba un test de la suite).",
    "- Los tests dados (copiados de tests_dados/) los escribe Claude: son la especificacion, no un cambio del "
    "implementador. Su CONTRATO (va en el diff) manda: lo que el contrato pide nunca es motivo de RECHAZAR.",
    "- Sin dependencias nuevas ni accesos a red salvo que la tarea los pida.",
)


# ================================================================ auditor (sin IA)
def auditar(diff: str, nivel_aprobado: str, tarea: dict) -> dict:
    fallos, avisos = [], []
    for b in riesgo._bloques(diff):
        ruta = b["ruta"]
        if I.no_enviable(ruta) or (b["origen"] and I.no_enviable(b["origen"])):
            fallos.append(f"{ruta}: privado, memoria/ o vault: el implementador nunca lo toca")
        codigo = bool(_CODIGO.search(ruta))
        for linea in b["anadidas"]:
            if codigo:
                for patron, desc in INSEGUROS:
                    if patron.search(linea):
                        fallos.append(f"{ruta}: valor inseguro (T226): {desc}: {linea.strip()[:80]}")
            if _REQ.search(ruta) and linea.strip() and not linea.strip().startswith(("#", "--hash")) \
                    and "==" not in linea:
                fallos.append(f"{ruta}: dependencia sin version fija: {linea.strip()[:60]}")
    c = riesgo.calcular(diff=diff, etiquetas=tarea.get("etiquetas") or ())
    if c["nivel"] == "R3":
        fallos.append("R3: " + "; ".join(c["motivos"]))
    avisos += [m for m in c["motivos"] if "dependencia" in m]
    return {"ok": not fallos, "fallos": list(dict.fromkeys(fallos)), "avisos": avisos, "nivel_real": c["nivel"]}


# ================================================================ tests dados (11/10)
def _leer_norm(ruta) -> str | None:
    try:
        return ruta.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None


def contrato_test_dado(repo, ruta: str, tope: int = 2500) -> str:
    """Bloque 23 (K0027): el docstring del test dado = el contrato que escribio Claude. El revisor solo veia "usalos
    como especificacion" sin la especificacion y rechazo T857 por hacer justo lo que el contrato pide."""
    import ast
    try:
        texto = ast.get_docstring(ast.parse((Path(repo) / ruta).read_text(encoding="utf-8"))) or ""
    except (OSError, SyntaxError, ValueError):
        return ""
    return texto if len(texto) <= tope else texto[:tope] + "\n[...recortado]"


def test_dado(repo, ruta: str) -> bool | None:
    """¿`ruta` (tests/...) es un test dado por Claude? True = identico a su copia de tests_dados/; False = existe la
    copia pero el archivo de la rama es distinto (el implementador lo toco); None = no es un test dado."""
    if not repo or not str(ruta).startswith("tests/"):
        return None
    original = _leer_norm(I.REPO / I.CARPETA_TESTS_DADOS / str(ruta).rsplit("/", 1)[-1])
    if original is None:
        return None
    return _leer_norm(Path(repo) / ruta) == original


def tests_dados_tocados(repo, diff: str) -> list[str]:
    """Tests dados que el implementador cambio respecto a la copia de Claude (nunca debe tocarlos)."""
    return [b["ruta"] for b in riesgo._bloques(diff) if test_dado(repo, b["ruta"]) is False]


# ================================================================ revisor de otra familia
def prompt_revision(tarea: dict, diff: str) -> str:
    partes = []
    for bloque in re.split(r"(?m)^(?=diff --git )", diff or ""):
        if not bloque.strip():
            continue
        m = re.match(r"diff --git a/(\S+) b/(\S+)", bloque)
        rutas = m.groups() if m else ()
        if any(I.no_enviable(r) for r in rutas):
            partes.append(f"[{rutas[-1]}: privado, memoria/ o vault: contenido omitido]\n")
        elif rutas and test_dado(tarea.get("_repo"), rutas[-1]):
            # 11/10 (T422): el revisor rechazaba porque "el diff crea un test de solo lectura". Los tests dados los
            # escribe Claude y se copian a la rama sin cambios (lo comprueba la puerta sin IA): no son del implementador.
            contrato = contrato_test_dado(tarea.get("_repo"), rutas[-1])
            partes.append(f"[{rutas[-1]}: tests dados escritos por Claude, copiados SIN CAMBIOS de "
                          f"{I.CARPETA_TESTS_DADOS}/ (comprobado sin IA). Que aparezcan en el diff es lo esperado: "
                          "no son un cambio del implementador. Usalos solo como especificacion.]\n"
                          + (f"CONTRATO de {rutas[-1]} (docstring escrito por Claude; el codigo debe cumplirlo):\n"
                             f"{contrato}\n[fin del contrato]\n" if contrato else ""))
        else:
            partes.append(bloque)
    cuerpo = "".join(partes)[:12000]
    simbolos = hechos.contexto_simbolos(tarea["_repo"], diff) if tarea.get("_repo") else ""
    contexto = ("SIMBOLOS DEFINIDOS EN LOS ARCHIVOS TOCADOS (leidos del repo, no del diff). No digas que algo no "
                "existe sin mirar esta lista; un verificador automatico anula esas acusaciones si el simbolo "
                f"existe:\n{simbolos}\n\n") if simbolos else ""
    return ("Eres revisor de codigo de NEXO. Otra IA implemento esta tarea. Revisa SOLO el diff.\n\n"
            f"TAREA {tarea.get('id', '')}: {tarea.get('titulo', '')}\n{(tarea.get('detalle') or '')[:1500]}\n\n"
            "LISTA FIJA:\n" + "\n".join(LISTA_REVISION) + "\n\n"
            "CONTRATOS DE NEXO (los exige la puerta; cumplirlos nunca es motivo de rechazo):\n"
            + "\n".join(CONTRATOS_NEXO) + "\n\n"
            f"{contexto}DIFF:\n{cuerpo}\n\n"
            "Responde exactamente con dos lineas:\nVEREDICTO: APROBAR o RECHAZAR\nMOTIVO: una frase\n")


def _candidatos():
    from nucleo import tribunal
    vistos, lista = set(), []
    from nucleo import banco_modelos   # T320: con evidencia clara del banco, su mejor revisor va delante
    for c in banco_modelos.ordenar("revisar", tribunal.TRIBUNAL + tribunal.APELACION, tribunal.clave_banco):
        if not c.web and c.id not in vistos:
            vistos.add(c.id)
            lista.append(c)
    return lista


def _disponible(c) -> bool:
    from nucleo import tribunal
    return tribunal._disponible(c)


def _proveedor_de(c):
    from nucleo import tribunal
    return tribunal._proveedor(c)


def _revisor_real(tarea: dict, diff: str, excluir: set[str]) -> dict:
    texto = prompt_revision(tarea, diff)
    for c in _candidatos():
        if c.familia in excluir or not _disponible(c):
            continue
        try:
            r = _proveedor_de(c).enviar(texto)
        except Exception as e:
            r = type("R", (), {"estado": "ERROR", "texto": str(e)})()
        m = re.search(r"VEREDICTO:\s*\**\s*(APROBAR|RECHAZAR)", getattr(r, "texto", "") or "", re.I)
        if getattr(r, "estado", "") == "OK" and m:
            mm = re.search(r"MOTIVO:\s*(.+)", r.texto)
            return {"veredicto": m.group(1).upper(), "revisor": c.id, "familia": c.familia,
                    "motivo": (mm.group(1).strip() if mm else "")[:300]}
    return {"veredicto": "SIN_REVISOR", "revisor": "", "familia": "", "motivo": "ningun revisor de otra familia"}


def _revisor(tarea: dict, diff: str, excluir: set[str]) -> dict:
    return _revisor_real(tarea, diff, excluir)


# ================================================================ principal
def resumen_rojos(salida: str, tope: int = 600) -> str:
    """Las lineas FAILED/ERROR de pytest (lo que de verdad fallo) y su ultima linea; si no hay, la cola de la salida.
    11/10: el motivo guardaba la cola (el resumen de avisos) y cortado a 300 car. no decia que test fallaba."""
    lineas = (salida or "").splitlines()
    rojos = [l.strip() for l in lineas if l.startswith(("FAILED ", "ERROR "))]
    if not rojos:
        return (salida or "")[-tope:]
    final = next((l.strip() for l in reversed(lineas) if l.strip()), "")
    return ("; ".join(rojos) + (f" ({final})" if final and final not in rojos else ""))[:tope]


def arbol_limpio(repo=None) -> bool:
    """Sin cambios sin commit en archivos versionados (los no versionados no cuentan: git no los toca).

    `memoria/` tampoco cuenta: la escribe NEXO todo el rato y el implementador tiene prohibido tocarla, asi que ni la
    fusion ni la marcha atras pasan nunca por ella. Cualquier otra ruta sucia sigue bloqueando.
    T1069: mientras haya un reparto de reels en marcha, el catalogo y documentacion/guias/*.md que esta escribiendo
    tampoco cuentan (al acabar la tanda los guarda el mismo en git); sin reparto en marcha, si."""
    salida = I._git(repo or I.REPO, "status", "--porcelain", "--untracked-files=no")
    sucias = []
    for linea in salida.splitlines():
        rutas = [p.strip().strip('"') for p in linea[3:].split(" -> ")]
        if linea.strip():
            sucias += [p for p in rutas if not p.startswith("memoria/")]
    if not sucias:
        return True
    from nucleo import reels_destino
    return all(reels_destino.es_generado(p) for p in sucias) and reels_destino.reparto_en_marcha()


def _salud_web() -> tuple[bool, str]:
    import httpx
    try:
        r = httpx.get("http://127.0.0.1:8765/salud", timeout=10)
    except Exception:
        return True, "web parada: no se comprueba /salud"
    return r.status_code == 200, f"/salud {r.status_code}"


REPETIR_SALUD = 1             # Bloque 21: veces que se repite la suite de salud si no da resultado (no si sale roja)


def _suite_salud(antes: str | None) -> tuple[bool, str, list[str]]:
    ok, salida = I._suite(I.REPO)
    previos = []
    if not ok and antes:
        ok, salida, previos = linea_base.filtrar(ok, salida, antes)
    return ok, salida, previos


def _salud(antes: str | None = None) -> tuple[bool, str]:
    """Suite en principal tras fusionar. T1027: con `antes` (principal justo antes de la fusion), los rojos que ya
    fallaban alli no son de la fusion y no la deshacen. Bloque 21: si la suite no da resultado (cerrojo ocupado o
    pasada de tiempo) se repite REPETIR_SALUD vez (el cerrojo espera a que este libre); si tampoco, NO se deshace (no
    hay rojo): queda fusionada con aviso para Claude."""
    sin_resultado = ""
    for vez in range(REPETIR_SALUD + 1):
        try:
            ok, salida, previos = _suite_salud(antes)
            break
        except I.FalloInfra as e:
            if vez == REPETIR_SALUD:
                ok, salida, previos = True, "", []
                sin_resultado = f"suite de salud SIN resultado {vez + 1} veces ({e}); no se deshace: no hay rojo. "
                _aviso("Salud sin comprobar tras fusionar", f"La suite de salud no dio resultado {vez + 1} veces "
                       f"({e}). La fusion se queda (no hay ningun rojo); que la compruebe Claude.", f"salud_infra:{antes}")
    if not ok:
        return False, f"suite en principal en rojo:\n{salida[-1200:]}"
    web_ok, detalle = _salud_web()
    detalle = sin_resultado + detalle
    if previos:
        detalle += f" (rojos que ya estaban antes de fusionar, no cuentan: {', '.join(previos)[:300]})"
    return web_ok, detalle


def _aviso(titulo: str, cuerpo: str, clave: str) -> None:
    from nucleo import avisos
    try:
        avisos.emitir("implementador", titulo, cuerpo, ruta="/#t-riesgo", clave=clave)
    except OSError:
        pass


def _nota(tid: str, texto: str) -> None:
    t = T.buscar(tid)
    if t and t["id"] == tid:
        T.anotar(tid, texto)


def pasar(tid: str, informe: dict | None = None) -> dict:
    """La puerta. Lo que anota en memoria/ (piloto, notas) va DESPUES de fusionar o revertir: si lo anotara antes,
    la propia puerta dejaria principal con cambios sin commit y nunca fusionaria (04/10, T462)."""
    r = _pasar(tid, informe)
    if "auditor" in r and I.en_piloto():
        I.registrar_puerta(tid, pasa=r["pasa"] if r["estado"] != "revertida" else True)
    for nota in r.pop("_notas", []):
        _nota(tid, nota)
    return r


def _pasar(tid: str, informe: dict | None = None) -> dict:
    inf = informe or I.cargar_informe(tid)
    if not inf or inf.get("estado") != "listo":
        return {"estado": "sin_implementacion", "pasa": False, "motivo": "no hay implementacion lista"}
    t = T.buscar(tid) or {"id": tid, "etiquetas": []}
    rama = f"impl/{tid}"
    # 04/10 (T462): se prueba lo que de verdad quedara en principal: la rama, al dia con principal.
    wt = inf["worktree"]
    I._git(wt, *I.FIRMA, "merge", "--no-edit", "-q", I.RAMA_BASE, check=False)
    if I._git(wt, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False).strip():
        I._git(wt, "merge", "--abort", check=False)
        return {"tarea": tid, "pasa": False, "estado": "conflicto", "solicitud": None,
                "motivo": "la rama choca con principal: vuelve al implementador"}
    diff = I.diff_rama(tid)
    r = {"tarea": tid, "pasa": False, "estado": "", "motivo": "", "solicitud": None, "_notas": []}

    try:
        ok, salida = I._suite(inf["worktree"])
        I.limpiar(inf["worktree"])
        # T1027: solo rechaza por rojos que NO esten ya en principal (mismo entorno, cacheado por commit). Antes T844,
        # T851, T854 y T862 cayeron por tests ajenos que fallaban en cualquier worktree.
        ok, salida, previos = linea_base.filtrar(ok, salida)
    except I.FalloInfra as e:     # Bloque 21: sin resultado no es un rojo: se repasa en la siguiente tanda
        I.limpiar(inf["worktree"])
        r.update(estado="espera_suite", motivo=f"{e}; se reintenta en la siguiente tanda")
        return r
    if previos:
        r["fallos_previos"] = previos
        r["_notas"].append(f"Puerta de fusion (T1027): {len(previos)} test(s) en rojo que ya fallaban en principal no "
                           f"cuentan: {', '.join(previos)[:400]}")
    fallos = [] if ok else [f"suite en rojo en la rama: {resumen_rojos(salida)}"]
    if inf.get("es_codigo") and not inf.get("tests_fallaban_antes"):
        fallos.append("no consta que los tests nuevos fallaran antes del cambio")
    a = auditar(diff, inf["nivel_aprobado"], t)
    fallos += a["fallos"]
    fallos += [f"{r}: el implementador cambio un test dado por Claude" for r in tests_dados_tocados(wt, diff)]
    rev = _revisor(dict(t, _repo=str(wt)), diff, {inf.get("familia", "")}) if not fallos         else {"veredicto": "NO_HACE_FALTA"}
    rev = hechos.verificar_rechazo(rev, wt)  # T685: una acusacion de "no existe" sobre algo que existe se anula
    if rev["veredicto"] != "APROBAR" and not fallos:
        fallos.append(f"revisor {rev.get('revisor') or '-'} ({rev.get('familia') or '-'}): {rev['veredicto']}: "
                      f"{rev.get('motivo', '')}")
    r.update(pasa=not fallos, revisor=rev, auditor=a)
    piloto = I.en_piloto()
    if fallos:
        r.update(estado="rechazada", motivo="; ".join(fallos))
        r["_notas"].append(f"Puerta de fusion (T669): NO pasa. {r['motivo'][:500]}")
        return r

    caso = I._cargar_piloto()["casos"].get(tid, {})
    if not inf.get("es_codigo") and not DOCUMENTACION_SIN_CLAUDE and caso.get("claude") != "FUSIONAR":
        r.update(estado="espera_claude", motivo="documentacion: solo entra con el FUSIONAR de Claude (la puerta aun no "
                                                "comprueba hechos contra el repo)")
        return r
    if piloto and caso.get("claude") is None:
        r.update(estado="espera_claude", motivo="piloto: nada se fusiona sin el FUSIONAR de Claude")
        return r

    # Fase 2 del piloto (04/10): con RECHAZAR de Claude el diff NO llega a la bandeja de Damian (ni tarjeta ni
    # contador): queda solo como informacion en el historial del piloto (casos de piloto.json). Con FUSIONAR, la
    # tarjeta R2 lleva el resumen en llano de Claude.
    if piloto and caso.get("claude") == "RECHAZAR":
        r.update(estado="rechazada_claude", motivo="piloto: Claude dijo RECHAZAR; queda en el historial del piloto")
        return r
    # Aqui ya hay suite verde, tests dados intactos, auditor OK y revisor APROBAR: puerta_ok (veto R1, Damian 13/10)
    f = riesgo.fusion(t, diff, inf["nivel_aprobado"], resumen=caso.get("resumen") or t.get("titulo", ""),
                      puerta_ok=True)
    r["solicitud"] = f["solicitud"]
    if f["destino"] == "claude":
        r.update(estado="r3", motivo=f["motivo"])
        return r
    if not f["puede"]:
        r.update(estado="espera_ok", motivo=f["motivo"])
        return r
    if not arbol_limpio():
        r.update(estado="espera_arbol_limpio", motivo="principal tiene cambios sin commit: se reintenta en la "
                                                       "siguiente tanda")
        return r

    mensaje = (f"Fusiona {rama}: {t.get('titulo', '')[:60]}\n\nImplementador: {tid}\nModelo: {inf.get('modelo')}\n"
               f"Puerta: suite verde, revisor {rev.get('revisor')} ({rev.get('familia')}), auditor OK, "
               f"nivel {f['nivel_real']}")
    antes = I._git(I.REPO, "rev-parse", "HEAD").strip()
    m = I._git(I.REPO, *I.FIRMA, "merge", "--no-ff", "--no-edit", "-m", mensaje, rama, check=False)
    if I._git(I.REPO, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False).strip():
        I._git(I.REPO, "merge", "--abort", check=False)
        r.update(estado="conflicto", motivo=f"la fusion choca con principal: {m[-300:]}")
        r["_notas"].append(f"Puerta de fusion (T669): conflicto con principal; vuelve al implementador.")
        return r
    if I._git(I.REPO, "rev-parse", "HEAD").strip() == antes:
        # T1069: git se nego a empezar (p. ej. la rama toca el catalogo que el reparto de reels tiene a medio escribir):
        # no hay fusion que probar ni que deshacer; se reintenta en la siguiente tanda.
        r.update(estado="espera_arbol_limpio", motivo=f"git no empezo la fusion: {m[-300:]}")
        return r
    if f["solicitud"]:
        from nucleo import aprobaciones as ap
        s = ap.ver(f["solicitud"])
        ap.consumir(s["id"], s["accion"], s["detalle"])
    fusion = I._git(I.REPO, "rev-parse", "HEAD").strip()
    r["fusion"] = fusion

    ok, detalle = _salud(antes)
    if not ok:
        I._git(I.REPO, *I.FIRMA, "revert", "-m", "1", "--no-edit", fusion)
        r.update(estado="revertida", motivo=f"salud tras fusionar: {detalle}", pasa=False)
        _aviso(f"Marcha atrás automática: {tid}", f"La fusión rompió la salud ({detalle[:200]}).", f"revert:{fusion}")
        r["_notas"].append(f"Implementador (T669): fusionada y DESHECHA (marcha atras automatica). Salud: {detalle[:500]}")
        tt = T.buscar(tid)
        if tt and tt["id"] == tid and tt["estado"] != "pendiente":
            T.actualizar(tid, estado="pendiente")
        return r
    r.update(estado="fusionada", motivo=detalle)
    r["_notas"].append(f"Implementador (T669): fusionada en principal ({fusion[:8]}) tras la puerta; salud: {detalle}.")
    return r
