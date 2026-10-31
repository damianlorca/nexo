"""Fase 3 (ACOTADA) de la auditoria: consulta a Qwen, Gemini y ChatGPT
para los 5 casos especiales de la Fase 4, segun el criterio que
confirmo Damian el 12/09/2026 (nada de barrido de 25-40 preguntas;
solo estos 5 casos; volumen bajo y espaciado; nada se implementa).

Va por lanzar() porque Gemini/ChatGPT tardan bastante por respuesta y
el puente corta a los 50s. Resultado en registros/fase3_multi_ia.json
(estructurado, para poder releerlo y montar la sintesis) y en
registros/fase3_multi_ia.txt (legible).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import logging  # noqa: E402
logging.disable(logging.INFO)

import proveedores  # noqa: E402
from extremidades import navegador  # noqa: E402


SALIDA_JSON = RAIZ / "registros" / "fase3_multi_ia.json"
SALIDA_TXT = RAIZ / "registros" / "fase3_multi_ia.txt"
SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)

lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto, flush=True)
    lineas.append(str(texto))
    SALIDA_TXT.write_text("\n".join(lineas), encoding="utf-8")


CASOS = [
    {
        "id": "A_despertar_claude",
        "requirement": "Despertar/activar una sesion de Claude Code bajo demanda desde el movil, sin esperar al turno programado de las 23:00",
        "current_state": "Ya implementado y probado: canal/bot.py (comando /ahora) dispara POST https://api.anthropic.com/v1/claude_code/routines/{id}/fire con un token propio de la rutina (Routines API trigger, no API key de pago), facturado contra el plan Claude Code existente, coste cero adicional. No devuelve la respuesta en la misma llamada: solo confirma que se ha pedido un turno; el resultado real llega despues por Telegram/memoria/estado.json cuando el turno termina.",
        "known_constraints": [
            "no usar Playwright/automatizacion de claude.ai (decision previa por ToS)",
            "no usar API de pago aparte del plan Claude Code ya contratado",
            "las credenciales las introduce Damian, nunca Nexo",
            "un solo turno de Claude a la vez: dos turnos simultaneos ya se pisaron la memoria una vez (incidente previo)",
        ],
        "why_current_approach_fails": "No falla para pedir UNA tarea de texto sin prisa. Si se necesita respuesta en segundos, o se quieren lanzar varias tareas independientes en paralelo sin que compartan/pisen la misma memoria de estado, no hay solucion todavia.",
        "question": "¿Hay alguna forma oficial (documentada o no) de reducir la latencia de este disparo, o de permitir varios turnos de Claude Code en paralelo sobre la misma rutina/dispositivo sin que se pisen la memoria compartida?",
    },
    {
        "id": "B_deteccion_limites_claude",
        "requirement": "Que el sistema sepa, antes de disparar un turno, si Claude Code tiene cuota disponible (limite de 5 horas y limite semanal), y en caso de no tenerla, cuando volvera a tenerla",
        "current_state": "No existe ningun mecanismo directo. Solo hay un contador propio (nucleo/uso.py) de cuantos turnos ha pedido Nexo, no de cuanta cuota real queda en la cuenta. Ya ha pasado un caso real: una rutina programada aparecio como FAILED en el historial, aparentemente por haber agotado el limite semanal, y solo se supo porque Damian vio un aviso en su propia app, no porque Nexo lo detectara.",
        "known_constraints": [
            "no hacer scraping/automatizacion de claude.ai con Playwright",
            "no usar cookies o sesion de la cuenta personal/principal de Damian",
            "no hay API publica documentada de consulta de cuota, hasta donde se ha podido comprobar",
        ],
        "why_current_approach_fails": "Solo se puede saber que se agoto la cuota DESPUES de intentar un turno y que falle (o de que Damian lo reporte manualmente). No hay forma de comprobarlo ANTES de gastar el intento.",
        "question": "¿Existe alguna senal indirecta razonable (cabeceras de la respuesta del endpoint de disparo de rutinas, algun otro endpoint no documentado pero estable, patrones en los codigos de error) que permita aproximar cuanta cuota de Claude Code queda antes de disparar un turno, sin hacer scraping de la interfaz web?",
    },
    {
        "id": "C_model_router",
        "requirement": "Decidir automaticamente, para cada tarea nueva, si la debe resolver Qwen (local, gratis, sin razonamiento fuerte), Gemini o ChatGPT (via navegador, gratis, mas lentos, con riesgo de bloqueo de cuenta si se abusa) o Claude (gasta el plan de pago), y dentro de Claude, que modelo/nivel de razonamiento usar",
        "current_state": "Hay piezas sueltas pero ningun router de verdad. nucleo/tareas.py calcula un 'modelo sugerido' (formula por dificultad+importancia) pero es solo informativo, nadie lo aplica solo. proveedores.py da una interfaz comun para invocar a los cuatro, pero no decide cual usar. Ademas esta CONFIRMADO que el modelo/nivel de una Rutina de Claude Code atada a un dispositivo NO se puede cambiar mecanicamente desde fuera: solo Damian puede cambiarlo aprobandolo el mismo desde su propio Claude Code.",
        "known_constraints": [
            "prioridad explicita: minimizar el gasto del plan de Claude",
            "Qwen es gratis pero lento y sin razonamiento fuerte (confirmado: un modelo pequeno razonando gasta su presupuesto de tokens pensando y no llega a contestar)",
            "Gemini/ChatGPT via navegador: gratis pero lentos (decenas de segundos por respuesta) y con riesgo real de bloqueo de cuenta si se usan en volumen alto o sin pausas",
            "el modelo/razonamiento de la Rutina de Claude no se puede cambiar de forma automatica: limitacion de la plataforma, no de diseno",
        ],
        "why_current_approach_fails": "No hay ningun componente que reciba una tarea nueva y decida activamente a que proveedor mandarla; solo hay una formula de sugerencia que nadie aplica y cuatro proveedores que hay que invocar a mano.",
        "question": "Dado que el modelo/nivel de razonamiento DENTRO de la rutina de Claude no se puede cambiar automaticamente (eso seguira dependiendo de que Damian lo apruebe el mismo), ¿cual es el diseno minimo y practico de un Model Router que si pueda decidir automaticamente entre Qwen / Gemini / ChatGPT / disparar-una-rutina-de-Claude segun dificultad, coste, latencia aceptable y necesidad de herramientas?",
    },
    {
        "id": "D_comunicacion_entre_ias",
        "requirement": "Que las distintas IAs (Qwen, Gemini, ChatGPT, Claude) se puedan pasar trabajo entre si de forma encadenada (p.ej. Qwen resume -> Gemini investiga -> ChatGPT redacta -> Claude revisa) sin que Damian tenga que copiar y pegar nada a mano, con una estructura de mensaje trazable",
        "current_state": "Hoy solo existe: (1) Qwen haciendo triaje de mensajes de Telegram (extremidades/triaje.py), y (2) cada proveedor invocable por separado con el mismo contrato minimo (proveedores.py: nombre/disponible()/estado()/enviar()/capacidades()). No hay ningun encadenamiento automatico entre proveedores, ni una estructura de mensaje con sender/receiver/task_id/message_type/payload/context/priority/timestamp/status/result/error, ni una cola o bus de mensajes entre IAs.",
        "known_constraints": [
            "minimizar el volumen de llamadas a Gemini/ChatGPT via navegador (riesgo de bloqueo de cuenta)",
            "nada de bucles desatendidos ni ráfagas de preguntas",
            "sin infraestructura nueva (sin bases de datos ni servicios externos de pago): tiene que apoyarse en archivos y lo que ya hay",
            "Claude solo se puede invocar completo via el disparo de una Rutina (no hay una llamada 'ligera' de Claude dentro de una cadena mas larga)",
        ],
        "why_current_approach_fails": "proveedores.py es solo un adaptador de transporte (mismo enviar()/estado() para los cuatro), no un protocolo de mensajes con identidad, estado y trazabilidad; no hay ninguna cola compartida donde una IA deje su resultado para que la siguiente lo recoja.",
        "question": "Usando solo archivos JSON con candado (como ya hace canal/buzon.py entre el agente y Telegram) o algo igual de simple, ¿que estructura minima de mensaje y de cola bastaria para encadenar 2-3 proveedores en una sola tarea, de forma trazable, sin montar infraestructura nueva?",
    },
    {
        "id": "E_autonomia_completa",
        "requirement": "Que Nexo pueda recibir un objetivo, dividirlo en subtareas, asignarlas, ejecutarlas, comprobarlas, corregirlas, reintentarlas, escalar a otra IA si hace falta, pedir autorizacion humana cuando corresponda, terminar, documentar, y proponer mejoras futuras, de forma sostenida (no solo dentro de un turno de Claude concreto)",
        "current_state": "Hoy todo el 'bucle de autonomia' ocurre dentro de la cabeza de un unico turno de Claude: un turno recibe un objetivo de Damian y lo ejecuta con sus propias herramientas en el mismo turno, sin dividirlo automaticamente en subtareas asignadas a otros proveedores. El sistema de tareas (nucleo.tareas) es un almacen con 5 estados (pendiente/en_curso/esperando/bloqueada/aparcada + cerrados), no una maquina de 10 fases. Existen piezas que podrian sostener algo mas: memoria/estado.json con una lista 'siguiente_turno', canal/vigilante.py como proceso que vive siempre en el PC (hoy solo relanza el bot de Telegram si muere).",
        "known_constraints": [
            "un solo turno de Claude a la vez (colision de memoria ya vista una vez)",
            "presupuesto de plan de Claude limitado, prioridad minimizarlo",
            "nunca proceder solo en decisiones irreversibles o genuinamente ambiguas: ahi se para y se pregunta (USER_DECISION_REQUIRED)",
            "nunca pedir credenciales ni codigos por ningun canal",
        ],
        "why_current_approach_fails": "En cuanto el turno de Claude concreto termina (o se corta porque se agota la cuota, como en el caso ya real de una rutina que salio FAILED), el trabajo se para ahi: ningun componente externo al turno retoma, reintenta o escala nada por su cuenta.",
        "question": "Con las piezas que ya existen (memoria/estado.json con 'siguiente_turno', nucleo/tareas.py, y canal/vigilante.py como proceso siempre vivo en el PC), ¿que diseno minimo permitiria que el ciclo OBSERVAR->PLANIFICAR->DELEGAR->EJECUTAR->VERIFICAR->CORREGIR->DOCUMENTAR sobreviva a que un turno concreto de Claude termine, sin construir un orquestador nuevo desde cero?",
    },
]


def preguntar_proveedor(proveedor, caso: dict) -> dict:
    contexto = json.dumps(
        {k: v for k, v in caso.items() if k != "id"}, ensure_ascii=False, indent=2
    )

    prompt = (
        "Contexto tecnico compacto de un requisito pendiente de un proyecto "
        "personal de automatizacion con IA (Nexo). Responde en espanol, "
        "de forma concreta y breve (maximo 200 palabras): como se podria "
        "implementar o aproximar esto, dadas las restricciones. No hace "
        "falta que repitas el contexto.\n\n" + contexto
    )

    inicio = time.time()

    try:
        r = proveedor.enviar(prompt)
        return {
            "estado": r.estado,
            "texto": r.texto,
            "detalle": r.detalle,
            "segundos": round(time.time() - inicio, 1),
        }
    except Exception as e:
        return {
            "estado": "ERROR",
            "texto": "",
            "detalle": f"{type(e).__name__}: {e}",
            "segundos": round(time.time() - inicio, 1),
        }


resultados: dict[str, dict] = {}

anotar(f"FASE 3 ACOTADA - CONSULTA MULTI-IA  {time.strftime('%Y-%m-%d %H:%M:%S')}")
anotar("=" * 70)
anotar(f"{len(CASOS)} casos especiales x 3 proveedores externos = "
       f"{len(CASOS) * 3} llamadas, secuenciales y espaciadas por la propia "
       "latencia de cada proveedor. Claude NO se dispara (su analisis lo "
       "hace directamente el turno que lea esto).")

qwen = proveedores.QwenProvider()

anotar("\n--- QWEN ---")
for caso in CASOS:
    anotar(f"\n[{caso['id']}] preguntando a Qwen...")
    r = preguntar_proveedor(qwen, caso)
    resultados.setdefault(caso["id"], {})["qwen"] = r
    anotar(f"  estado={r['estado']}  {r['segundos']}s")
    anotar(f"  {r['texto'][:600] if r['texto'] else r['detalle']}")

    SALIDA_JSON.write_text(
        json.dumps({"casos": CASOS, "resultados": resultados}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

if not navegador.activo():
    anotar("\nChrome no estaba activo, arrancando...")
    navegador.arrancar()
    time.sleep(5)

gemini = proveedores.GeminiProvider()

anotar("\n--- GEMINI ---")
for caso in CASOS:
    anotar(f"\n[{caso['id']}] preguntando a Gemini...")
    r = preguntar_proveedor(gemini, caso)
    resultados.setdefault(caso["id"], {})["gemini"] = r
    anotar(f"  estado={r['estado']}  {r['segundos']}s")
    anotar(f"  {r['texto'][:600] if r['texto'] else r['detalle']}")

    SALIDA_JSON.write_text(
        json.dumps({"casos": CASOS, "resultados": resultados}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    time.sleep(8)

chatgpt = proveedores.ChatGPTProvider()

anotar("\n--- CHATGPT ---")
for caso in CASOS:
    anotar(f"\n[{caso['id']}] preguntando a ChatGPT...")
    r = preguntar_proveedor(chatgpt, caso)
    resultados.setdefault(caso["id"], {})["chatgpt"] = r
    anotar(f"  estado={r['estado']}  {r['segundos']}s")
    anotar(f"  {r['texto'][:600] if r['texto'] else r['detalle']}")

    SALIDA_JSON.write_text(
        json.dumps({"casos": CASOS, "resultados": resultados}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    time.sleep(8)

anotar("\n" + "=" * 70)
anotar("FIN_FASE3")
