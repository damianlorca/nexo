# Bloque 13 — arreglos pequeños del modo foco (18/10/2026)

## HECHO Y TESTEADO (10 tareas cerradas con `completar(despues, cierre)` + el cierre a mano de la web)
| Tarea | Qué | Dónde | Tests |
|---|---|---|---|
| T1013 | Un 403 sin texto de cuota es transitorio: enfría 30 min; la primera llamada tras caducar sondea (otro 403 → bloqueo 6 h, éxito → se borra). El 401 sigue terminal. | `nucleo/fallos.py`, `nucleo/enfriamiento.py` | `test_t157_fallos.py` (+4) |
| (web) | Cerrar a mano desde la ficha: «después» y evidencia vienen rellenados y editables; un clic cierra. | `_tarea_detalle.html` | `interfaz/tests/test_tareas.py` (+1, ruta) |
| T427 | Todo prompt de delegación lleva fecha y hora de Madrid (sin `tzdata`: regla europea de respaldo). | `nucleo/ahora.py`, `trabajo.py`, `tribunal.py`, `chat_tarea.py` | `test_t427_fecha_en_prompts.py` (6) |
| T195 | Orden de llamada editable en Ajustes y respetado por `trabajo.py` (generadores y revisores). | `nucleo/orden_proveedores.py`, `ajustes.py`, `_ajustes_orden.html` | 5 + 1 de ruta |
| T561 | El auditor no deja salir material interno/privado hacia NVIDIA Trial en `trabajo.py` (autor y revisor). **El tribunal NO** (ver abajo). | `nucleo/auditor.py`, `trabajo.py` | `test_t561_...` (4) |
| T928 / T929 / T931 / T048 | ComfyUI: terminar limpio si falla `_anotar`; identidad con hora de creación y registro borrado al matar; un HTTP de error ya no se disfraza de timeout; arrancar pasa por `nucleo/permisos`. | `extremidades/imagen.py` | `test_imagen.py` (29, 10 nuevos) |
| T842 / T843 | `aplicar_n01.py`: comprobar que el archivo existe antes de devolverlo a CRLF; `--ignore-whitespace` solo si algún archivo tocado es CRLF. | `documentacion/propuestas/aplicar_n01.py` | `test_t842_t843_aplicar_n01.py` (3, repo git real) |

## HECHO SIN APLICAR — diffs para que Damián los vea (`nucleo/permisos.py` es blindado)
Verificados en una copia del repo: sobre HEAD fallan los tests nuevos; con el diff pasan todos los de permisos. Los dos aplican limpios sobre el repo actual, solos o juntos.

1. `documentacion/diffs/guardia_T830_T832_T841.patch` — **T830** (format.com, vssadmin.exe, reg.exe, cipher.exe, HKEY_LOCAL_MACHINE), **T832** (inicio de comando tras salto de línea) y **T841** (`''` en comillas simples; comilla a mitad de palabra → línea no simple). Incluye `tests/test_permisos_guardia_n05.py` (27 tests). T841 cierra un hueco real: `git log a'b ; curl http://x ; c'd` salía VERDE.
   Efecto a confirmar (T832): una orden multilínea con `rm`/`del`/`format` al principio de una línea pasa a ROJO.
2. `documentacion/diffs/guardia_T831_git_commit_add.patch` — **T831** (sacar `commit` y `add` de `GIT_INERTES`). **Choca con T024**: `git commit -m "instale winget"` pasa de VERDE a AMBAR y `git commit -m "quitar rm -rf del script"` a ROJO; el diff cambia esos dos tests. Va aparte para decidirlo por separado.

Aplicar: `git apply documentacion/diffs/<archivo>.patch` (y luego la suite). T830, T831, T832 y T841 siguen `pendiente` con la nota; se cierran al aplicar.

## Decisiones / desviaciones
- **T561 y el tribunal:** lo apliqué primero también al tribunal y rompió `test_tres_primeros_disponibles...`: con material interno y autor ChatGPT, sin NVIDIA solo quedan 2 familias y no se llega a 3/3. Lo retiré (commit `f1d0825`); el tribunal queda como estaba. **Decisión de Damián:** aceptar un tribunal de 2 con material interno, o dejarlo así.
- **Un commit por tarea:** no se pudo en dos casos porque tocan el mismo archivo: ComfyUI (T928/T929/T931/T048 en `imagen.py`) y T842/T843 (`aplicar_n01.py`). Cada commit lista sus tareas.
- **T929:** la ventana entre comprobar la identidad y `taskkill` se estrecha (PID + línea + hora de creación) pero no desaparece; no hay manejador de proceso entre sesiones. Anotaciones antiguas sin hora de creación siguen valiendo con PID + línea.
- **T048:** el arranque sigue siendo `subprocess.Popen` directo (migrar a `manos.shell.lanzar` falló 3/3 el 14/09 y cambia el PID); ahora exige `nivel_de_comando` y `nivel_de_ruta` antes. El arranque real es VERDE.
- Tests de T195/T427 usan los fixtures de aislamiento existentes; `tests/conftest.py` redirige `orden_proveedores.ARCHIVO` para no tocar `memoria/`.
