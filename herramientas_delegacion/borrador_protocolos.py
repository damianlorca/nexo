# -*- coding: utf-8 -*-
"""T137 (bloque B4): borrador de protocolos delegado a Gemini API (respaldo: Qwen).
Claude lo revisa despues. Nunca publica nada: solo deja el borrador."""
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
VAULT = RAIZ.parent / "contexto" / "proyectos" / "nexo"

fuentes = [RAIZ / "CLAUDE.md", RAIZ / "documentacion" / "handoff-semana-sin-claude.md", VAULT / "protocolos.md"]
contexto = "\n\n".join(f"=== {f.name} ===\n{f.read_text(encoding='utf-8')[:12000]}" for f in fuentes if f.is_file())

PROMPT = (
    "Eres redactor tecnico. Con SOLO la informacion de estos documentos, escribe en espanol el documento "
    "'Protocolos de uso y funcionamiento de NEXO v1'. Publico: Damian (el dueno, no programador de NEXO) y cualquier IA "
    "que trabaje en NEXO. Maximo 900 palabras, Markdown, secciones cortas con listas numeradas. Secciones obligatorias:\n"
    "1. Como le da ordenes Damian a NEXO (Telegram: mensajes sueltos, /tarea, /tareas, /hecha, /estado, /parar, /seguir).\n"
    "2. Como trabaja NEXO sin Claude (proveedores y orden de uso; que NO hace solo).\n"
    "3. Revision y verificacion (Principio de Verdad; estados de una tarea).\n"
    "4. Permisos y seguridad (verde/ambar/rojo, archivos blindados, guardia de Python, secretos).\n"
    "5. Handoffs (cuando se escriben, que deben contener, donde viven).\n"
    "6. Cola de tareas y catalogo (donde estan, quien los edita, como se priorizan).\n"
    "7. Parada de emergencia.\n"
    "No inventes funciones que no aparezcan en los documentos. Si algo no esta claro, escribe 'PENDIENTE DE DEFINIR'.\n\n"
    + contexto
)

from proveedores import GeminiAPIProvider, QwenProvider  # noqa: E402

r = GeminiAPIProvider(timeout=90).enviar(PROMPT)
autor = "gemini_api"
if not r.ok:
    print("Gemini API fallo:", r.detalle[:200], "-> Qwen")
    r = QwenProvider().enviar(PROMPT)
    autor = "qwen"
salida = RAIZ / "memoria" / "borradores" / f"T137_protocolos_{autor}_{datetime.now():%Y%m%d_%H%M}.md"
salida.parent.mkdir(parents=True, exist_ok=True)
salida.write_text(f"<!-- BORRADOR de {autor}, SIN REVISAR por Claude -->\n\n" + (r.texto or f"[{r.estado}] {r.detalle}"), encoding="utf-8")
print(r.estado, autor, salida)
