"""27/09/2026 Damian: investigacion + posible implementacion (o extraccion de lo interesante) de OpenClaw, Hermes Agent,
Muse, Grok bot y Obscura (en vez de Chrome). Sin duplicar: se enlazan T142/T110/T152 y lo ya adoptado."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

PLANTILLA = (
    "\nFORMATO OBLIGATORIO (T192): 1) identidad exacta (URL oficial, autor, licencia, actividad) - si hay varios candidatos "
    "con ese nombre, listarlos y elegir con motivo, nunca suponer; 2) que hace y como (arquitectura); 3) piezas utiles para "
    "NEXO con el archivo de NEXO donde encajarian; 4) riesgos (seguridad, ToS, coste, Windows); 5) veredicto ADOPTAR / "
    "ADAPTAR / EXTRAER IDEAS / DESCARTAR; 6) seccion PROPUESTAS IMPLEMENTABLES (que, donde, valor 1-5, esfuerzo 1-5, riesgo) "
    "para que se creen las tareas de implementacion. Datos no comprobados marcados [SIN VERIFICAR]."
)
YA = "Ya adoptado de estos sistemas (NO repetir): T143 enfriamiento, T158 contenido no confiable, T160 verify-on-stop, T154 revisor ambar; en curso T144/T145/T155/T156/T157."

nuevas = [
    ("Investigar a fondo OpenClaw y extraer lo aprovechable para NEXO (segunda pasada)",
     "Damian 27/09. Segunda pasada, a nivel de codigo, tras T142. " + YA + " Buscar lo que falta: gestion de canales, permisos, "
     "skills, memoria, orquestacion, interfaz." + PLANTILLA, ["tema:orquestacion"]),
    ("Investigar a fondo Hermes Agent y extraer lo aprovechable para NEXO (segunda pasada)",
     "Damian 27/09. Segunda pasada, a nivel de codigo, tras T142. " + YA + " Buscar lo que falta: memoria por capas, skills que "
     "se aprenden, planificador, verificacion, bucle de agente." + PLANTILLA, ["tema:orquestacion"]),
    ("Investigar Muse y extraer lo aprovechable para NEXO",
     "Damian 27/09. Mencionado de pasada en T110. Primero IDENTIFICAR cual es (hay varios productos/proyectos llamados Muse): "
     "el relacionado con agentes/IA/asistentes." + PLANTILLA, ["tema:recursos_por_identificar"]),
    ("Investigar 'Grok bot' y extraer lo aprovechable para NEXO",
     "Damian 27/09. Grok como PROVEEDOR ya se audito en T152; aqui interesa como bot/agente (funciones de agente, tareas, "
     "integraciones, API). Identificar exactamente a que se refiere 'grok bot' antes de investigar." + PLANTILLA,
     ["tema:modelos_proveedores_roles"]),
    ("Investigar Obscura como sustituto de Chrome para el navegador de NEXO",
     "Damian 27/09: valorar usar Obscura en vez del Chrome de NEXO (extremidades/navegador.py, Playwright por CDP 9333). "
     "Identificar exactamente que es Obscura (navegador/headless para agentes). Comparar con el Chrome actual: sesiones con "
     "login de Google/ChatGPT (hoy en chrome-perfil), deteccion de bots/captcha, compatibilidad Playwright/CDP, consumo de RAM, "
     "Windows, estabilidad, seguridad. Criterio: solo sustituir si mejora sin romper T188/T193 (modo Pensar, candado, lectura "
     "fiable); proponer prueba en paralelo, no migracion directa." + PLANTILLA, ["tema:modelos_proveedores_roles"]),
]
ids = []
for titulo, detalle, extra in nuevas:
    t = T.anadir(titulo, detalle=detalle, importancia=4, urgencia=3, dificultad=2, coste=2, depende="ia",
                 etiquetas=["cat:investigacion", "circuito_revision", "origen:damian_chat"] + extra)
    ids.append(t["id"])
T.anotar("T142", f"27/09: la segunda pasada se divide en {ids[0]} (OpenClaw) y {ids[1]} (Hermes).")
T.anotar("T110", f"27/09: Muse y Grok pasan a tareas propias {ids[2]} y {ids[3]}.")
print(" ".join(ids))
