# -*- coding: utf-8 -*-
"""T669 (04/10): NADA que lance el implementador abre un navegador. Se carga solo (PYTHONPATH) en el proceso de Aider.

Por que: en el piloto, Aider con --yes-always acepto 30 veces "Open URL for more info?" (errores de cuota de Groq y
Gemini, documentacion de Aider) y abrio pestanas en el Chrome PERSONAL de Damian. Una variable BROWSER no basta: si
su comando no existe, `webbrowser` cae en el navegador por defecto. Aqui se sustituye el modulo entero por una
funcion que solo anota la URL (NEXO_URLS_BLOQUEADAS) y dice que "se abrio", para que nadie busque otro navegador.
"""
import os
import webbrowser

_LOG = os.environ.get("NEXO_URLS_BLOQUEADAS", "")


def _nulo(url, *args, **kwargs):
    if _LOG:
        try:
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(f"{url}\n")
        except OSError:
            pass
    return True


class _SinNavegador(webbrowser.BaseBrowser):
    def open(self, url, new=0, autoraise=True):
        return _nulo(url)


_NULO = _SinNavegador("nexo-sin-navegador")
webbrowser.open = webbrowser.open_new = webbrowser.open_new_tab = _nulo
webbrowser.get = lambda using=None: _NULO
webbrowser._browsers = {"nexo-sin-navegador": [None, _NULO]}
webbrowser._tryorder = ["nexo-sin-navegador"]   # ya no se registran los del sistema (ni BROWSER ni Chrome)
webbrowser._nexo_bloqueado = True

# 04/10, fase 2: Aider abre el repo con git.GitDB (lector de objetos en Python puro), que solo lee los paquetes
# `pack-*.pack`. `git maintenance` (tarea loose-objects) mete objetos en paquetes `loose-*.pack` que GitDB no ve:
# BadObject al listar los archivos y ninguna tarea del implementador arranca. Se usa el lector que habla con git.
try:
    import git
    git.GitDB = git.GitCmdObjectDB
except Exception:       # sin GitPython (otro Python): no hay nada que parchear
    pass
