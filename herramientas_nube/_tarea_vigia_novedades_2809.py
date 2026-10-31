"""28/09/2026 Damian: rol de investigacion continua (vigia de novedades)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

t = T.anadir(
    "Rol 'vigia de novedades': investigacion continua diaria de repos, skills, modelos y herramientas utiles para NEXO",
    detalle=(
        "Damian 28/09: un rol que cada dia (en el turno, con plantilla propia de T231) busque novedades utiles para NEXO y "
        "las apunte para investigar/implementar: repos de GitHub (agentes, orquestacion, memoria, interfaz), skills de "
        "Claude/agentes, modelos nuevos (y sus benchmarks), modelos GRATIS nuevos en Ollama, NVIDIA build, Groq y OpenRouter, "
        "cambios en las webs/APIs de ChatGPT y Gemini que afecten a NEXO.\n"
        "Reglas: (1) fuentes fijas y verificables (GitHub trending/releases, ollama.com/library, build.nvidia.com/models via "
        "/models, changelogs oficiales), sin inventar; (2) deduplicar contra tareas.json y el catalogo de herramientas antes de "
        "apuntar nada; (3) cada hallazgo entra como tarea 'propuesta' con fuente, fecha y por que interesa, y pasa por el "
        "circuito T192 (Claude revisa antes de investigar a fondo o implementar); (4) tope diario (p. ej. 5 hallazgos) para no "
        "llenar la cola; (5) resumen semanal en la web. Lo hacen proveedores gratuitos/locales, nunca Claude."),
    importancia=4, urgencia=3, dificultad=2, coste=1, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:orquestacion", "origen:damian_chat"])
T.anotar("T231", f"28/09: anadir la plantilla de turno 'vigia de novedades' ({t['id']}).")
print(t["id"])
