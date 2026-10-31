"""03/10/2026: epica del plan revision->aprobacion->implementacion + equipo 24/7."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

ep = T.anadir(
    "EPICA: revision -> aprobacion -> implementacion sin depender de Claude",
    detalle=("Damian 03/10: prioridad sobre el backlog. Plan en documentacion/PLAN_REVISION_APROBACION_IMPLEMENTACION.md "
             "(fases F0 freno y filtro, F1 tribunal de revision con calibracion, F2 matriz de riesgo y bandeja, "
             "F3 implementador en rama con puerta de fusion y marcha atras, F4 backlog, F5 ajuste). Pendiente de aprobacion "
             "de Damian antes de empezar F0."),
    importancia=5, urgencia=5, dificultad=4, coste=3, depende="damian",
    etiquetas=["cat:arquitectura", "prov:claude", "tema:orquestacion", "origen:damian_chat", "epica"])

pc = T.anadir(
    "Equipo fijo 24/7 para NEXO: seleccion de componentes y transicion desde el portatil",
    detalle=("Damian 03/10: esta preparando con ChatGPT un documento con los componentes para montar un PC dedicado a NEXO "
             "en casa (24 h). Recoger ese documento en documentacion/hardware/, revisar la configuracion contra las "
             "necesidades reales de NEXO (modelos locales que se quieran correr, RAM y VRAM, consumo electrico 24/7, ruido, "
             "arranque solo tras corte de luz, Wake-on-LAN T037, acceso por Tailscale) y preparar el plan de migracion "
             "(repo, venv, Ollama y modelos, Chrome NEXO con sesiones, tareas, Tailscale, copias de seguridad). "
             "Relacionado: T138 (estudio de equipo 24/7)."),
    importancia=4, urgencia=3, dificultad=3, coste=2, depende="damian",
    etiquetas=["cat:operacion_pc", "prov:claude", "tema:hardware", "origen:damian_chat"])
T.anotar("T138", f"03/10: continua en {pc['id']} con el documento de componentes de Damian.")
print(ep["id"], pc["id"])
