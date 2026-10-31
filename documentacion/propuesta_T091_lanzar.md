# T091 segunda pieza — `lanzar()` con scripts .py a través de la guardia (PROPUESTA, sin aplicar)

**Problema.** `ejecutar_python()` ya pasa por `nucleo/guardia_python.py`. En cambio, `lanzar(".venv\Scripts\python.exe script.py")` solo comprueba el texto del comando: lo que el script haga por dentro no se vigila. En la práctica Claude usa `lanzar()` para todo lo que dura más de 50 s, y hoy lo ha hecho envolviendo a mano con `nucleo\guardia_python.py` (depende de la disciplina de Claude, no de una regla).

**Cambio propuesto** en `manos/servidor_mcp.py`, que es un archivo blindado y necesita el visto bueno de Damián:

```diff
 def lanzar(comando: str, nombre: str = "proceso", cwd: str = "", aprobado: bool = False) -> str:
-    return _envuelto(
-        lambda: shell.lanzar(comando, nombre, cwd or None, aprobado)
-    )
+    if not aprobado:
+        comando = _con_guardia(comando)
+    return _envuelto(
+        lambda: shell.lanzar(comando, nombre, cwd or None, aprobado)
+    )
+
+
+_PY_SCRIPT = re.compile(r'^(?P<py>"?[^"\s]*pythonw?(?:\.exe)?"?)\s+(?P<script>(?!-)[^\s"]+\.py)(?P<resto>(\s.*)?)$', re.I)
+
+
+def _con_guardia(comando: str) -> str:
+    """Si el comando es `python script.py ...`, lo pasa por nucleo/guardia_python.py (T091)."""
+    m = _PY_SCRIPT.match(comando.strip())
+    if not m or m.group("script").replace("/", "\\").lower().endswith("nucleo\\guardia_python.py"):
+        return comando
+    return f'{m.group("py")} {RAIZ / "nucleo" / "guardia_python.py"} {m.group("script")}{m.group("resto") or ""}'
```

**No cubre** `python -m modulo` ni `cmd /c ...` compuestos. Se anota como pendiente.

**Pruebas previstas:**
1. `lanzar(".venv\Scripts\python.exe x.py")` con un x.py que escribe fuera de la zona → GuardiaBloqueo en el log.
2. Con `aprobado=True` el script se lanza sin guardia.
3. Chrome, el bot y ComfyUI (no son `.py` sueltos o ya van por `-m`) se lanzan igual que antes.
4. Reiniciar el servidor MCP.
