"""03/10/2026: Damian aprueba el plan y las recomendaciones de Claude. Traza fases como tareas + revision multi-IA del plan."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from nucleo import tareas as T  # noqa: E402

DOC = "documentacion/PLAN_REVISION_APROBACION_IMPLEMENTACION.md"
plan = (RAIZ / DOC).read_text(encoding="utf-8")
plan = plan.replace("Estado: **PROPUESTA, pendiente de que Damián la apruebe**",
                    "Estado: **APROBADO por Damián el 03/10/2026** (matriz de riesgo, límites 30/15/14 días y revisión multi-IA en paralelo con F0)")
(RAIZ / DOC).write_text(plan, encoding="utf-8")

T.actualizar("T664", depende="ia")
T.anotar("T664", "03/10 Damian APRUEBA el plan completo: matriz de riesgo con veto R1 de 24 h (silencio = si), limites 30 propuestas "
                 "abiertas / 15 revisiones pendientes / caducidad 14 dias, y revision multi-IA del plan en paralelo con F0.")

fases = [
    ("F0 Freno y filtro: limite de trabajo en curso, pausa de turnos generadores, caducidad 14 dias y filtro automatico del backlog",
     "Seccion 3.1 y fase F0 del plan. Limites aprobados: 30 propuestas abiertas, 15 revisiones pendientes, caducidad 14 dias "
     "(archivar con motivo, recuperable). Filtro sin IA: formato incompleto, duplicados (similitud con tareas abiertas y cerradas "
     "30 dias), sin fuentes, valor<=2 con esfuerzo>=4; fusion de parecidas. Aplicarlo a las 242 propuestas actuales en modo "
     "simulacion primero (informe de que se archivaria y por que), y despues de verdad. Panel minimo: entradas/salidas por semana "
     "y tamano de la cola. Tests.", 5, 5, 3),
    ("F1 Tribunal de revision con verificacion de hechos y calibracion por muestra de Claude",
     "Secciones 3.2-3.4 del plan. 3 revisores de familias distintas (propuesta: ChatGPT Pensar, Gemini Pro, mejor NVIDIA), "
     "sin ver al autor; verificacion de hechos T288 + T334 (hacer T334 aqui); unanimidad = REVISADA/DESCARTADA, resto = ESCALADA "
     "con resumen del desacuerdo; muestra aleatoria a Claude 30%->10% (coincidencia >=90% en 50 casos), retroceso por debajo de "
     "85%, por tipo de trabajo. Panel de coincidencia y escalados.", 5, 5, 4),
    ("F2 Matriz de riesgo fija y bandeja de aprobaciones con veto R1 por push y OK R2 de un toque",
     "Seccion 4 del plan. Nivel calculado por codigo segun rutas y acciones; el tribunal solo puede subirlo. R0 auto; R1 auto con "
     "push 'se implementara X salvo que digas NO' (24 h, silencio = si); R2 boton Aprobar con resumen humano y diff resumido; R3 "
     "parche para Damian. Integra T077 (bandeja web).", 5, 4, 3),
    ("F3 Implementador independiente: herramienta elegida con prueba, rama por tarea, puerta de fusion, marcha atras y piloto",
     "Seccion 5 del plan. Comparar con prueba corta Aider / OpenHands / opencode (T169) / Kilo Code (T184) con modelos gratuitos "
     "(T320). Worktree por tarea, tests primero, limites por nivel (R0/R1 ~300 lineas, rutas permitidas, sin blindados), 2 "
     "intentos maximo. Puerta: suite + tests nuevos + diff revisado por otra familia + auditor; fusion R0/R1 automatica, R2 espera "
     "OK; salud tras fusionar y revert automatico. Piloto de 10-15 tareas R0/R1 con todos los diffs revisados por Claude.", 5, 4, 5),
    ("F4 Pasar el backlog por el sistema (filtro + tribunal); Claude solo escalados y muestra",
     "Fase F4 del plan. Tras F0-F2.", 4, 3, 2),
]
ids = []
for titulo, det, imp, urg, dif in fases:
    t = T.anadir(titulo, detalle=det + f" Plan: {DOC}. Epica T664.", importancia=imp, urgencia=urg, dificultad=dif, coste=2,
                 depende="ia", etiquetas=["cat:arquitectura", "prov:claude", "tema:orquestacion", "epica:T664"])
    ids.append(t["id"])

rev = T.anadir(
    "Revision multi-IA del plan revision-aprobacion-implementacion hasta OK absoluto",
    detalle=("Revisa criticamente este plan de NEXO (orquestador local-first de Damian en Windows: IA local + ChatGPT/Gemini web "
             "+ NVIDIA/Groq gratis + Claude Code para programar). Objetivo: que NEXO revise, apruebe e implemente sus mejoras sin "
             "depender de Claude salvo en lo importante. Busca FALLOS de diseno, OMISIONES, riesgos no cubiertos, puntos donde "
             "el sistema se pueda saturar o colar errores, y MEJORAS concretas. Contrasta con practicas reconocidas (revision por "
             "pares, CI/CD con puertas, despliegue progresivo, calibracion de evaluadores). No reescribas el plan entero: lista "
             "cambios concretos con su motivo, y en PROPUESTAS IMPLEMENTABLES los que deberian incorporarse.\n\nPLAN:\n" + plan),
    importancia=5, urgencia=5, dificultad=2, coste=1, depende="ia",
    etiquetas=["cat:investigacion", "prov:chatgpt", "tema:orquestacion", "material:interno", "extension:larga",
               "circuito_revision", "epica:T664"])
T.anotar("T664", f"03/10: fases creadas {', '.join(ids)}; revision multi-IA del plan en {rev['id']}.")
print("fases:", ids, "revision:", rev["id"])
