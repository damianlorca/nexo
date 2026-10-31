# -*- coding: utf-8 -*-
"""Publicacion nocturna del espejo de GitHub (T890 punto 10; OK de Damian del 16/10).

El espejo (herramientas_nube/publicar_nube.py: copia limpia de HEAD, sin datos privados y con los tokens sustituidos)
llevaba parado desde el 12/10 porque solo se publicaba a mano al cerrar turno. Ahora el planificador lo ejecuta UNA
vez al dia, en la primera vuelta a partir de las 03:00, y nunca con la PARADA puesta (se queda pendiente: sale en la
primera vuelta con la parada quitada). Si no hay cambios, el script no hace nada (sale con 0).

- Un proceso aparte y en un hilo: el tick del planificador no espera a git ni a la red.
- Un dia = un intento: se marca ANTES de lanzar (no se relanza en cada tick aunque falle).
- Si falla (codigo != 0: 2 = el remoto tiene cambios que no son un espejo, 1 = error) o no termina, un aviso en el
  Centro, como mucho 1 al dia. Nunca se imprime ni guarda nada que no sea la ultima salida del script (que ya no
  imprime secretos).

Estado: memoria/espejo/ultimo.json = {dia, cuando, codigo, salida}. CLI: .venv\\Scripts\\python.exe -m nucleo.espejo estado
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, time as hora_t
from pathlib import Path

from nucleo.config import RAIZ
from nucleo.escritura import escribir_atomico

REPO = RAIZ
CARPETA = RAIZ / "memoria" / "espejo"
SCRIPT = RAIZ / "herramientas_nube" / "publicar_nube.py"
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
DESDE = hora_t(3, 0)           # primera vuelta a partir de esta hora
TIMEOUT_S = 900                # el script hace git + un push: 15 min es mucho
LANZADOR = None                # los tests lo sustituyen (conftest): nunca un proceso real desde un tick de prueba


def _ultimo() -> dict:
    try:
        d = json.loads((CARPETA / "ultimo.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def ultimo() -> dict:
    return _ultimo()


def toca(ahora: datetime) -> bool:
    """A partir de las 03:00 y sin intento hoy."""
    return ahora.time() >= DESDE and _ultimo().get("dia") != ahora.strftime("%Y-%m-%d")


def _ejecutar() -> tuple[int, str]:
    """Corre el script (codigo, ultimas lineas de salida). TimeoutExpired/OSError las trata quien llama."""
    r = subprocess.run([str(PYTHON if PYTHON.is_file() else sys.executable), str(SCRIPT)], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _resumir(salida: str) -> str:
    return " | ".join(x.strip() for x in salida.strip().splitlines()[-4:])[:400]


def _avisar(dia: str, titulo: str, cuerpo: str) -> None:
    try:
        from nucleo import avisos
        clave = f"espejo:{dia}"
        if not avisos.ya_emitido(clave):     # emitir() solo frena 1 h: un aviso al dia
            avisos.emitir("espejo", titulo, cuerpo, ruta="/", clave=clave, urgencia="normal")
    except Exception:   # noqa: BLE001 - avisar nunca rompe
        pass


def _trabajo(dia: str, ejecutar) -> dict:
    cuando = datetime.now().isoformat(timespec="seconds")
    try:
        codigo, salida = ejecutar()
    except subprocess.TimeoutExpired:
        codigo, salida = -1, f"no termino en {TIMEOUT_S} s"
    except Exception as e:   # noqa: BLE001
        codigo, salida = -1, f"{type(e).__name__}: {str(e)[:200]}"
    res = {"dia": dia, "cuando": cuando, "codigo": codigo, "salida": _resumir(salida)}
    try:
        CARPETA.mkdir(parents=True, exist_ok=True)
        escribir_atomico(CARPETA / "ultimo.json", json.dumps(res, ensure_ascii=False, indent=1))
    except OSError:
        pass
    if codigo != 0:
        motivo = ("el remoto tiene cambios que no son un espejo: hay que traerlos a local" if codigo == 2
                  else "error al publicar" if codigo == 1 else "no se pudo ejecutar")
        _avisar(dia, "El espejo de GitHub no se ha publicado",
                f"publicar_nube.py ({motivo}; codigo {codigo}): {res['salida']}. Se reintenta mañana a las 03:00; "
                "a mano: .venv\\Scripts\\python.exe herramientas_nube\\publicar_nube.py")
    return res


def repaso_si_toca(ahora: datetime | None = None, ejecutar=None, en_hilo: bool = True) -> str | None:
    """Lo llama el planificador en cada tick. Devuelve lo que hizo o None. Con PARADA puesta no hace nada ni marca el
    dia (queda pendiente para la primera vuelta sin parada)."""
    ahora = ahora or datetime.now()
    if not toca(ahora):
        return None
    from nucleo import parada
    if parada.activa():
        return None
    dia = ahora.strftime("%Y-%m-%d")
    CARPETA.mkdir(parents=True, exist_ok=True)
    escribir_atomico(CARPETA / "ultimo.json", json.dumps(          # el dia queda marcado ANTES de lanzar
        {"dia": dia, "cuando": ahora.isoformat(timespec="seconds"), "codigo": None, "salida": "en curso"}))
    ejecutar = ejecutar or LANZADOR or _ejecutar
    if en_hilo:
        threading.Thread(target=_trabajo, args=(dia, ejecutar), name="espejo-nocturno", daemon=True).start()
        return "espejo lanzado"
    res = _trabajo(dia, ejecutar)
    return f"espejo: codigo {res['codigo']}"


def _cli(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["estado"]:
        print(json.dumps(_ultimo() or {"dia": None}, ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 0 if argv[:1] in ([], ["-h"], ["--help"]) else 2


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # noqa: E702  (incidente 05/10: --help antes de nada)
    sys.exit(_cli(sys.argv[1:]))
