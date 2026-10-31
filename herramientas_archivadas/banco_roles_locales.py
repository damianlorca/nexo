"""Banco de pruebas de roles para IA local (T100, ronda 29, 22/09/2026).

Objetivo: decidir con evidencia real (no a ojo) que modelo de Ollama cubre
cada rol propuesto en el plan de T100 (Proyecto NEXO:
claude/plan-ias-locales-roles.md):
  1. clasificador rapido (triaje/routing)
  2. worker de criterio medio (estimar importancia/urgencia)
  3. worker de borrador de codigo
  4. reviewer (segunda opinion barata, nivel REVIEWED/CONSENSUS)

No toca produccion (no importa router.py/bot.py/canal/*), no decide nada
por su cuenta -- solo mide y escribe un informe para que Damian y Claude
lo revisen juntos. Pensado para lanzarse una vez, de un tiron, sin
supervision (los 3 guardarrailes del plan de T100): numero de casos fijo y
acotado (nunca un bucle abierto), criterio de exito objetivo siempre que es
posible (ejecucion real de codigo con asserts, comparacion con datos reales
ya fijados por Damian en tareas.json), nunca se autoevalua como "bien
hecho" sin esa evidencia -- solo escribe los datos, la decision la toman
Damian y Claude despues.

Uso: .venv\\Scripts\\python.exe banco_roles_locales.py
Lanzado la noche del 22/09/2026 via manos.shell.lanzar() (proceso
independiente, sigue corriendo aunque la sesion de Claude que lo lanzo
termine). Escribe registros/banco_roles_<fecha>.md (+ .json con datos
crudos) y deja una nota en T100 al terminar.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from openai import OpenAI

from nucleo import tareas as T
from nucleo.config import RAIZ

OLLAMA = "http://localhost:11434/v1"
MINIMO_TOKENS = 600
TIMEOUT = 240

INFORME = RAIZ / "registros" / f"banco_roles_{time.strftime('%Y%m%d_%H%M%S')}.md"


def _cliente() -> OpenAI:
    return OpenAI(base_url=OLLAMA, api_key="local", timeout=TIMEOUT, max_retries=1)


def preguntar(modelo: str, instruccion: str, texto: str = "", max_tokens: int = 1200) -> tuple[str, float]:
    contenido = f"{instruccion}\n\n{texto}".strip()
    t0 = time.perf_counter()

    try:
        r = _cliente().chat.completions.create(
            model=modelo,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres una herramienta de ejecucion, no un asistente. "
                        "Responde solo lo pedido, sin comentarios ni explicaciones extra."
                    ),
                },
                {"role": "user", "content": contenido},
            ],
            max_tokens=max(max_tokens, MINIMO_TOKENS),
            temperature=0.2,
        )
        salida = r.choices[0].message.content or ""
    except Exception as e:
        salida = f"ERROR: {e}"

    dur = round(time.perf_counter() - t0, 1)
    salida = re.sub(r"<think>.*?</think>", "", salida, flags=re.DOTALL | re.IGNORECASE).strip()

    return salida, dur


resultados: dict[str, list[dict]] = {"clasificador": [], "criterio": [], "codigo": [], "reviewer": []}

# ---------------------------------------------------- 1. Clasificador rapido
MODELOS_CLASIFICADOR = ["qwen3:4b", "llama3.2:3b", "qwen2.5:7b"]

CASOS_ROUTER = [
    (
        "Clasifica el texto en UNA de estas categorias: resumen, extraccion, otro. Responde solo con la categoria.",
        "Resume este texto: Nexo es un orquestador de IA que combina modelos locales y externos para ejecutar tareas con supervision minima.",
        "resumen",
    ),
    (
        "Clasifica el texto en UNA de estas categorias: resumen, extraccion, otro. Responde solo con la categoria.",
        "Extrae el nombre del responsable y el proyecto de: 'El responsable es Damian y el proyecto es Nexo.' Claves: responsable, proyecto",
        "extraccion",
    ),
    (
        "Clasifica el texto en UNA de estas categorias: resumen, extraccion, otro. Responde solo con la categoria.",
        "Cuentame un chiste sobre gatos.",
        "otro",
    ),
    (
        "Clasifica el texto en UNA de estas categorias: resumen, extraccion, otro. Responde solo con la categoria.",
        "Cuanto es 2+2?",
        "otro",
    ),
]

CASOS_TAREA = [
    (
        "Clasifica el texto en UNA de estas categorias: tarea, no_tarea. 'tarea' significa que "
        "la persona quiere que se apunte como pendiente para hacer luego. Responde solo con la categoria.",
        "apunta que hay que revisar el pipeline de datos la semana que viene",
        "tarea",
    ),
    (
        "Clasifica el texto en UNA de estas categorias: tarea, no_tarea. 'tarea' significa que "
        "la persona quiere que se apunte como pendiente para hacer luego. Responde solo con la categoria.",
        "no quiero que lo apuntes como tarea, quiero que me contestes",
        "no_tarea",
    ),
    (
        "Clasifica el texto en UNA de estas categorias: tarea, no_tarea. 'tarea' significa que "
        "la persona quiere que se apunte como pendiente para hacer luego. Responde solo con la categoria.",
        "que hora es en Tokio ahora mismo?",
        "no_tarea",
    ),
    (
        "Clasifica el texto en UNA de estas categorias: tarea, no_tarea. 'tarea' significa que "
        "la persona quiere que se apunte como pendiente para hacer luego. Responde solo con la categoria.",
        "hay que arreglar el bug del encoding en shell.py",
        "tarea",
    ),
]

for modelo in MODELOS_CLASIFICADOR:
    for casos, nombre_grupo in ((CASOS_ROUTER, "router"), (CASOS_TAREA, "tarea")):
        for instr, texto, esperado in casos:
            salida, dur = preguntar(modelo, instr, texto, max_tokens=600)
            acierto = esperado.lower() in salida.lower()
            resultados["clasificador"].append({
                "modelo": modelo, "grupo": nombre_grupo, "texto": texto[:60],
                "esperado": esperado, "salida": salida.strip()[:80],
                "acierto": acierto, "segundos": dur,
            })

# --------------------------------------------------------- 2. Worker de criterio
MODELOS_CRITERIO = ["qwen2.5:7b", "qwen3:14b", "qwen3.8:27b"]

_datos = T.cargar()
_candidatas = [
    t for t in _datos["tareas"]
    if t["estado"] in T.CERRADOS and len((t.get("detalle") or "")) > 80
][:4]

for modelo in MODELOS_CRITERIO:
    for t in _candidatas:
        instr = (
            "Lee esta tarea real de un proyecto y estima, en una escala de 1 a 5, "
            "su IMPORTANCIA (cuanto cambia si sale bien) y su URGENCIA (cuanto duele "
            "el retraso). Responde EXACTAMENTE en este formato, sin nada mas: "
            "importancia=N urgencia=N"
        )
        texto = f"Titulo: {t['titulo']}\n\nDetalle: {(t.get('detalle') or '')[:600]}"
        salida, dur = preguntar(modelo, instr, texto, max_tokens=300)

        m_imp = re.search(r"importancia\s*=\s*(\d)", salida)
        m_urg = re.search(r"urgencia\s*=\s*(\d)", salida)
        est_imp = int(m_imp.group(1)) if m_imp else None
        est_urg = int(m_urg.group(1)) if m_urg else None

        resultados["criterio"].append({
            "modelo": modelo, "tarea": t["id"],
            "importancia_real": t["importancia"], "importancia_estimada": est_imp,
            "urgencia_real": t["urgencia"], "urgencia_estimada": est_urg,
            "diff_imp": (abs(est_imp - t["importancia"]) if est_imp is not None else None),
            "diff_urg": (abs(est_urg - t["urgencia"]) if est_urg is not None else None),
            "segundos": dur,
        })

# ------------------------------------------------- 3. Worker de borrador de codigo
MODELOS_CODIGO = ["qwen3-coder:30b", "devstral-small-2:24b", "qwen2.5:7b"]

SPECS_CODIGO = [
    {
        "nombre": "es_palindromo",
        "instruccion": (
            "Escribe SOLO una funcion Python llamada es_palindromo(s: str) -> bool "
            "que devuelva True si el texto es un palindromo, ignorando mayusculas/"
            "minusculas y espacios. Sin explicaciones, sin markdown, solo el codigo "
            "Python de la funcion."
        ),
        "tests": [
            "assert es_palindromo('Anita lava la tina') == True",
            "assert es_palindromo('hola') == False",
            "assert es_palindromo('') == True",
        ],
    },
    {
        "nombre": "invertir_lista",
        "instruccion": (
            "Escribe SOLO una funcion Python llamada invertir_lista(lst: list) -> list "
            "que devuelva la lista invertida SIN usar reversed() ni lst[::-1] ni "
            ".reverse(). Sin explicaciones, sin markdown, solo el codigo Python."
        ),
        "tests": [
            "assert invertir_lista([1,2,3]) == [3,2,1]",
            "assert invertir_lista([]) == []",
            "assert invertir_lista([5]) == [5]",
        ],
    },
]


def extraer_codigo(salida: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", salida, flags=re.DOTALL)
    return m.group(1) if m else salida


def probar_codigo(codigo: str, tests: list[str]) -> tuple[int, int, str]:
    ok = 0
    errores = []

    for assertion in tests:
        script = codigo + "\n\n" + assertion + "\nprint('OK')"

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(script)
            ruta = f.name

        try:
            r = subprocess.run(
                [sys.executable, ruta], capture_output=True, text=True, timeout=10,
            )

            if r.returncode == 0 and "OK" in r.stdout:
                ok += 1
            else:
                errores.append((r.stderr or r.stdout)[:200])

        except Exception as e:
            errores.append(str(e)[:200])

        finally:
            Path(ruta).unlink(missing_ok=True)

    return ok, len(tests), " | ".join(errores)[:300]


for modelo in MODELOS_CODIGO:
    for spec in SPECS_CODIGO:
        salida, dur = preguntar(modelo, spec["instruccion"], max_tokens=1500)
        codigo = extraer_codigo(salida)
        ok, total, errores = probar_codigo(codigo, spec["tests"])

        resultados["codigo"].append({
            "modelo": modelo, "spec": spec["nombre"],
            "tests_ok": ok, "tests_total": total,
            "errores": errores, "segundos": dur,
        })

# --------------------------------------------------------------- 4. Reviewer
MODELOS_REVIEWER = ["gpt-oss:20b", "qwen2.5:7b"]

CASOS_REVISION = [
    (
        "¿Es correcto este JSON como respuesta a 'extrae responsable y proyecto, "
        "claves: responsable, proyecto'? Respuesta: "
        '{"responsable": "Damian", "proyecto": "Nexo"}. Responde SOLO si o no.',
        "si",
    ),
    (
        "¿Es correcto este JSON como respuesta a 'extrae responsable y proyecto, "
        "claves: responsable, proyecto'? Respuesta: "
        '{"responsable": "Damian", "proyecto": "Nexo", "extra": "dato de mas"}. '
        "Responde SOLO si o no.",
        "no",
    ),
    (
        "¿Es un resumen valido de 'Nexo es un orquestador de IA local-first que "
        "coordina modelos para ejecutar tareas con supervision minima' esta respuesta: "
        "'Nexo es un orquestador de IA local-first que coordina modelos para ejecutar "
        "tareas con supervision minima'? (ojo: es identico al original, no resume "
        "nada). Responde SOLO si o no.",
        "no",
    ),
    (
        "¿Es un resumen valido de 'Nexo es un orquestador de IA local-first que "
        "coordina modelos para ejecutar tareas con supervision minima' esta respuesta: "
        "'Nexo coordina IA local y externa para hacer tareas solo.'? Responde SOLO si o no.",
        "si",
    ),
]

for modelo in MODELOS_REVIEWER:
    for pregunta, esperado in CASOS_REVISION:
        salida, dur = preguntar(modelo, pregunta, max_tokens=400)
        acierto = esperado in salida.lower()

        resultados["reviewer"].append({
            "modelo": modelo, "pregunta": pregunta[:70], "esperado": esperado,
            "salida": salida.strip()[:60], "acierto": acierto, "segundos": dur,
        })


# ----------------------------------------------------------------- Informe

def resumen_por_modelo(items: list[dict], campo_acierto: str = "acierto") -> dict:
    agregados = defaultdict(lambda: {"aciertos": 0, "total": 0, "segundos": 0.0})

    for it in items:
        m = it["modelo"]
        agregados[m]["total"] += 1
        agregados[m]["segundos"] += it.get("segundos", 0)

        if it.get(campo_acierto):
            agregados[m]["aciertos"] += 1

    return agregados


lineas = []
lineas.append("# Banco de pruebas de roles de IA local (T100)\n")
lineas.append(
    f"_Generado automaticamente el {time.strftime('%Y-%m-%d %H:%M:%S')}, lanzado "
    "por Claude sin supervision para que Damian y Claude lo revisen juntos. "
    "Ningun resultado de aqui se aplico solo a produccion -- es solo evidencia "
    "para decidir. Plan completo en el Proyecto NEXO: "
    "claude/plan-ias-locales-roles.md._\n"
)

lineas.append("## 1. Clasificador rapido (candidato a triaje/routing)\n")
ag = resumen_por_modelo(resultados["clasificador"])
lineas.append("| modelo | aciertos | total | seg. promedio |")
lineas.append("|---|---|---|---|")
for m, d in sorted(ag.items(), key=lambda kv: -kv[1]["aciertos"] / max(kv[1]["total"], 1)):
    prom = round(d["segundos"] / max(d["total"], 1), 1)
    lineas.append(f"| {m} | {d['aciertos']}/{d['total']} | {d['total']} | {prom}s |")
lineas.append("\n<details><summary>Detalle caso por caso</summary>\n")
for it in resultados["clasificador"]:
    marca = "OK" if it["acierto"] else "FALLO"
    lineas.append(
        f"- [{marca}] {it['modelo']} ({it['grupo']}) — \"{it['texto']}\" "
        f"→ esperado={it['esperado']}, salida=\"{it['salida']}\" ({it['segundos']}s)"
    )
lineas.append("\n</details>\n")

lineas.append(
    "## 2. Worker de criterio (estimar importancia/urgencia de tareas reales "
    "ya decididas por Damian)\n"
)
lineas.append("| modelo | tarea | importancia real→estimada | urgencia real→estimada | diff total |")
lineas.append("|---|---|---|---|---|")
for it in resultados["criterio"]:
    diff = (it["diff_imp"] if it["diff_imp"] is not None else 9) + (
        it["diff_urg"] if it["diff_urg"] is not None else 9
    )
    lineas.append(
        f"| {it['modelo']} | {it['tarea']} | "
        f"{it['importancia_real']}→{it['importancia_estimada']} | "
        f"{it['urgencia_real']}→{it['urgencia_estimada']} | {diff} |"
    )
if not resultados["criterio"]:
    lineas.append("(sin tareas cerradas con detalle suficiente para probar -- omitido)")

lineas.append("\n## 3. Worker de borrador de codigo (verificacion mecanica: tests ejecutados de verdad)\n")
lineas.append("| modelo | spec | tests OK | segundos |")
lineas.append("|---|---|---|---|")
for it in resultados["codigo"]:
    lineas.append(f"| {it['modelo']} | {it['spec']} | {it['tests_ok']}/{it['tests_total']} | {it['segundos']}s |")
    if it["errores"]:
        lineas.append(f"  - errores: {it['errores']}")

lineas.append("\n## 4. Reviewer (segunda opinion sobre respuestas ya generadas, con y sin error inyectado)\n")
ag = resumen_por_modelo(resultados["reviewer"])
lineas.append("| modelo | aciertos | total |")
lineas.append("|---|---|---|")
for m, d in ag.items():
    lineas.append(f"| {m} | {d['aciertos']}/{d['total']} | {d['total']} |")

lineas.append("\n## Notas\n")
lineas.append(
    "- JSON crudo de todos los resultados en el archivo hermano con extension "
    ".json, por si hace falta reanalizar sin re-ejecutar nada."
)
lineas.append(
    "- No se ha tocado router.py/canal/bot.py/nucleo/tareas.py -- este script "
    "solo lee tareas.json (nunca escribe en el, salvo la nota final en T100) "
    "y llama directamente a Ollama."
)

INFORME.parent.mkdir(parents=True, exist_ok=True)
INFORME.write_text("\n".join(lineas), encoding="utf-8")
INFORME.with_suffix(".json").write_text(
    json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
)

try:
    T.anotar(
        "T100",
        f"Banco de pruebas de roles completado automaticamente (sin supervision, "
        f"corrido la noche del 22/09). Informe en registros/{INFORME.name} "
        f"(+ .json con datos crudos). Pendiente de que Damian y Claude lo "
        f"revisen juntos y decidan los roles finales, o rediseñen otra prueba "
        f"a partir de esto.",
    )
except Exception as e:
    print(f"aviso: no se pudo anotar T100 ({e}), el informe si se escribio")

print(f"Hecho. Informe: {INFORME}")
