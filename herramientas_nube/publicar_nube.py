"""Publica un ESPEJO LIMPIO del repo en GitHub para las sesiones en la nube.

Por que un espejo y no `git push` normal (decidido el 25/09/2026):
- El historial local contiene memoria/becas.md (datos privados, Damian
  decidio tratarlo como privado) y una cadena con forma de token de
  Telegram en un test. Reescribir el historial local rompe la
  trazabilidad; un push normal subiria ese historial entero.
- Solucion: se construye un arbol a partir de HEAD (solo lo commiteado),
  quitando rutas privadas y sustituyendo cualquier cosa con forma de
  token por un valor falso, y se publica como un commit nuevo encima del
  ultimo espejo. El historial local no se toca y nunca sale del PC.

Reglas:
- Si el remoto tiene un commit que NO es un espejo (alguien fusiono un PR
  directamente en GitHub), se aborta: primero hay que traer ese cambio a
  local; si no, el espejo lo pisaria.
- Si aparece una clave privada (-----BEGIN ... PRIVATE KEY-----) se aborta
  (no se redacta: eso no deberia estar en el repo).
- Nunca imprime el valor de un secreto: solo ruta y numero de
  sustituciones.
- Sin remoto configurado: no hace nada y sale con 0 (apto para el cierre
  de turno).

Uso:
  python herramientas_nube/publicar_nube.py            # publica en 'origin'
  python herramientas_nube/publicar_nube.py --seco     # construye y revisa, no sube
  python herramientas_nube/publicar_nube.py --remoto RUTA_O_URL
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RAMA_REMOTA = "principal"
REF_LOCAL = "refs/nube/principal"
PREFIJO = "Espejo de "

# Rutas que NUNCA salen del PC (prefijos, estilo git).
EXCLUIR = (
    "memoria/becas.md",
    "memoria/historial_telegram.json",
    "canal/entrada/",
    "canal/estado_bot.json",
    "memoria/chats_tareas/",          # T290: conversaciones de Damian con el chat de cada tarea
    "memoria/perfil_privado/",        # T750: CV y datos personales de Damian
    "memoria/radares/perfil.json",    # T750: perfil que usan los radares
)

FALSO_TELEGRAM = "123456789:" + "A" * 35
PATRONES_REDACTAR = (
    (re.compile(rb"\d{8,10}:[A-Za-z0-9_-]{35}"), FALSO_TELEGRAM.encode()),
    (re.compile(rb"AIza[0-9A-Za-z_-]{35}"), b"AIza" + b"X" * 35),
    (re.compile(rb"sk-[A-Za-z0-9_-]{20,}"), b"sk-FALSO" + b"X" * 20),
    (re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,}"), b"ghp_" + b"X" * 36),
)
PATRON_ABORTAR = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")

# Sustituciones solo para una ruta concreta. config.toml va al espejo
# (decision 7 del 26/09), pero sin el chat_id real de Telegram: Damian,
# 27/09. Un chat_id que ya es 0 no cuenta como sustitucion.
REDACTAR_POR_RUTA = {
    "config.toml": (
        (re.compile(rb"(?m)^(chat_id[ \t]*=[ \t]*)0*[1-9]\d*"), rb"\g<1>0"),
    ),
}


def redactar(ruta: str, datos: bytes) -> tuple[bytes, int]:
    """Devuelve (datos redactados, numero de sustituciones). No imprime nada."""
    total = 0
    for patron, falso in PATRONES_REDACTAR + REDACTAR_POR_RUTA.get(ruta, ()):
        datos, n = patron.subn(falso, datos)
        total += n
    return datos, total


def git(*args: str, env: dict | None = None, entrada: bytes | None = None,
        comprobar: bool = True) -> bytes:
    r = subprocess.run(["git", *args], cwd=RAIZ, env=env, input=entrada,
                       capture_output=True)
    if comprobar and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} fallo: "
                           f"{r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def excluida(ruta: str) -> bool:
    return any(ruta == e or (e.endswith("/") and ruta.startswith(e))
               for e in EXCLUIR)


def construir_arbol() -> tuple[str, list[str], list[str]]:
    """Devuelve (sha_arbol, rutas_excluidas, informe_redacciones)."""
    fd, indice = tempfile.mkstemp(prefix="nube_idx_")
    os.close(fd)
    os.unlink(indice)
    env = {**os.environ, "GIT_INDEX_FILE": indice}
    try:
        git("read-tree", "HEAD", env=env)
        filas = git("ls-files", "-s", "-z", env=env).split(b"\0")
        fuera, informe = [], []
        for fila in filas:
            if not fila:
                continue
            meta, ruta_b = fila.split(b"\t", 1)
            modo, sha, _ = meta.decode().split()
            ruta = ruta_b.decode("utf-8", errors="surrogateescape")
            if excluida(ruta):
                git("update-index", "--force-remove", "--", ruta, env=env)
                fuera.append(ruta)
                continue
            if modo == "160000":  # submodulo
                continue
            datos = git("cat-file", "blob", sha)
            if b"\0" in datos[:8000]:  # binario
                continue
            if PATRON_ABORTAR.search(datos):
                raise RuntimeError(f"clave privada en {ruta}: ABORTADO")
            nuevo, total = redactar(ruta, datos)
            if total:
                sha_n = git("hash-object", "-w", "--stdin",
                            entrada=nuevo).decode().strip()
                git("update-index", "--cacheinfo", f"{modo},{sha_n},{ruta}",
                    env=env)
                informe.append(f"{ruta}: {total} sustitucion(es)")
        arbol = git("write-tree", env=env).decode().strip()
        return arbol, fuera, informe
    finally:
        if os.path.exists(indice):
            os.unlink(indice)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remoto", default="origin")
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()

    remotos = git("remote").decode().split()
    es_nombre = a.remoto in remotos
    if not es_nombre and not (("/" in a.remoto) or ("\\" in a.remoto)):
        print(f"Sin remoto '{a.remoto}': nada que publicar.")
        return 0

    arbol, fuera, informe = construir_arbol()
    print(f"Arbol limpio: {arbol[:10]}  excluidas={len(fuera)}  "
          f"redactadas={len(informe)}")
    for linea in informe:
        print("  redactado ->", linea)

    # Ultimo espejo publicado (si existe).
    padre = ""
    ls = git("ls-remote", a.remoto, f"refs/heads/{RAMA_REMOTA}").decode().strip()
    if ls:
        git("fetch", "-q", a.remoto, f"+{RAMA_REMOTA}:{REF_LOCAL}")
        padre = git("rev-parse", REF_LOCAL).decode().strip()
        msg = git("log", "-1", "--format=%s", padre).decode()
        if not msg.startswith(PREFIJO):
            print("ABORTADO: el remoto tiene cambios que no son un espejo "
                  f"({msg.strip()[:60]}). Trae primero esos cambios a local.")
            return 2
        if git("rev-parse", f"{padre}^{{tree}}").decode().strip() == arbol:
            print("Sin cambios desde el ultimo espejo.")
            return 0

    cabeza = git("log", "-1", "--format=%h %s").decode().strip()
    args = ["commit-tree", arbol, "-m", f"{PREFIJO}{cabeza}"]
    if padre:
        args[2:2] = ["-p", padre]
    commit = git(*args).decode().strip()
    if a.seco:
        print(f"SECO: se publicaria {commit[:10]} (padre {padre[:10] or '-'})")
        return 0
    git("push", "-q", a.remoto, f"{commit}:refs/heads/{RAMA_REMOTA}")
    git("update-ref", REF_LOCAL, commit)
    print(f"Publicado {commit[:10]} en {a.remoto}/{RAMA_REMOTA}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print("ERROR:", e)
        sys.exit(1)
