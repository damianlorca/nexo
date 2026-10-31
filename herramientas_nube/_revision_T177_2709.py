"""Revision de Claude del borrador T177 (gstack), 27/09/2026, y evidencia para T188/T189."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

T.anotar("T177", "27/09 REVISADO POR CLAUDE (borrador T177_20260927_1320.md): gstack = garrytan/gstack, skills para Claude Code "
                 "(plan/review/QA/ship con navegador headless), MIT, Bun+Git Bash en Windows. VEREDICTO: solo referencia, NO instalar. "
                 "Solapa con Superpowers (ya instalado: planes, TDD, verificacion, code review) y cada skill extra gasta contexto en "
                 "cada sesion. Unica idea aprovechable: QA de la interfaz en navegador real a 375/412 px antes de cerrar un hito "
                 "(Code ya lo hace a mano). Cifras de estrellas/issues del borrador SIN VERIFICAR. Sin propuestas nuevas de implementacion.")
T.completar("T177", "Revisado por Claude el 27/09: solo referencia, no se adopta.")
T.anotar("T188", "27/09 T177: otra vez sin Pensar en ChatGPT (13:12 y 13:17).")
T.anotar("T189", "27/09 evidencia en T177_20260927_1320.md: (1) la version final lleva basura de la UI de ChatGPT "
                 "('ChatGPT dijo:', 'Mostrar mas', 'Ultima respuesta', 'GitHub +1'); (2) el prompt de mejora pego ENTERAS las "
                 "revisiones y el borrador (prompt inflado, lo que Damian describe); (3) el revisor groq pidio cosas sin valor "
                 "(tutorial Hello World, comparativa con LangChain/AutoGPT) y nadie las filtro. El auditor debe limpiar la lectura del DOM, "
                 "resumir las revisiones antes de reenviarlas y descartar peticiones de revisores fuera de alcance.")
print("ok")
