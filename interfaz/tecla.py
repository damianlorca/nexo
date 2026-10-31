"""Tecla Copilot -> NEXO, como un interruptor (24/10).

Uso: .venv\\Scripts\\pythonw.exe -m interfaz.tecla   (lo llama interfaz\\scripts\\abrir_nexo_app.bat, que es lo que
PowerToys ejecuta al pulsar la tecla Copilot).

- Si la ventana de NEXO (Edge en modo aplicacion) no existe: la abre entrando con el token de este arranque.
- Si existe y esta delante: la minimiza.
- Si existe pero esta minimizada o detras de otra: la trae delante.
Asi pulsar la tecla dos veces ya no abre una ventana nueva.

La ventana se reconoce por su titulo (todas las paginas de la web acaban en " · NEXO"), por ser de msedge.exe y por no
llevar " - Microsoft Edge" (eso es una pestana normal del navegador, que no se toca).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TOKEN = RAIZ / "memoria" / "interfaz_token.txt"
URL = "http://127.0.0.1:8765/entrar?t={}"
SUFIJO = "· NEXO"


def decidir(existe: bool, minimizada: bool, delante: bool) -> str:
    """'abrir' | 'traer' | 'minimizar'."""
    if not existe:
        return "abrir"
    if minimizada or not delante:
        return "traer"
    return "minimizar"


def es_ventana_nexo(titulo: str, proceso: str) -> bool:
    t = (titulo or "").strip()
    return (proceso or "").lower() == "msedge.exe" and t.endswith(SUFIJO) and "Microsoft" not in t


def _ventana():   # pragma: no cover - solo Windows real
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    encontrada = []

    def proceso_de(hwnd) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(1024)
            ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
            return Path(buf.value).name if ok else ""
        finally:
            kernel32.CloseHandle(h)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        largo = user32.GetWindowTextLengthW(hwnd)
        if largo:
            buf = ctypes.create_unicode_buffer(largo + 1)
            user32.GetWindowTextW(hwnd, buf, largo + 1)
            if es_ventana_nexo(buf.value, proceso_de(hwnd)):
                encontrada.append(hwnd)
                return False
        return True

    user32.EnumWindows(cada, 0)
    return encontrada[0] if encontrada else None


def _abrir() -> int:   # pragma: no cover - solo Windows real
    if not TOKEN.is_file():
        return 1
    token = TOKEN.read_text(encoding="utf-8").strip()
    os.startfile("msedge", "open", f'--app="{URL.format(token)}"')
    return 0


def main() -> int:   # pragma: no cover - solo Windows real
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = _ventana()
    accion = decidir(hwnd is not None, bool(hwnd and user32.IsIconic(hwnd)),
                     bool(hwnd and user32.GetForegroundWindow() == hwnd))
    if accion == "abrir":
        return _abrir()
    if accion == "minimizar":
        user32.ShowWindow(hwnd, 6)          # SW_MINIMIZE
        return 0
    # traer: minimizar y restaurar la pone delante aunque Windows bloquee SetForegroundWindow
    if not user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 6)
    user32.ShowWindow(hwnd, 9)              # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ))
    from nucleo import ayuda
    ayuda.atender(__doc__)
    raise SystemExit(main())
