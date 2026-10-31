# -*- coding: utf-8 -*-
"""Banco de pruebas T100 v2: roles/ (adaptados de agency-agents, T130) frente
a un prompt generico con el MISMO formato de salida, en modelos locales.

Rediseñado tras el incidente del 23/09 (el v1 colgo el PC al cargar modelos de
24-30B sin guardas; ver contexto/proyectos/nexo/referencia-incidentes-tecnicos.md):
  - Solo los modelos de MODELOS (por defecto <=8B). Uso:
        python banco_roles_v2.py                 -> qwen3:4b, llama3.2:3b, qwen2.5:7b
        python banco_roles_v2.py qwen3:14b       -> solo ese (con Damian delante)
  - API nativa /api/chat con num_ctx=4096 (el endpoint /v1 carga 32K e
    ignora keep_alive: 6,9 GB para un 7B).
  - Antes de cargar cada modelo: >= RAM_MINIMA_GB libres o se salta.
  - Un modelo cada vez y `ollama stop` al acabar cada uno.
  - Durante la prueba, si la RAM libre baja de RAM_CORTE_GB, se para ese modelo.

Que mide: para cada modelo x rol x prompt (rol|generico), cuantos casos
aciertan el veredicto esperado (o, en 'codigo', entregan un diff minimo y
correcto) y cuantos devuelven la salida BIEN FORMADA, mas la latencia.
El prompt generico solo contiene el formato de salida: la diferencia entre
ambos es exactamente el valor de las reglas del rol.
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

import roles

MODELOS_POR_DEFECTO = ["qwen3:4b", "llama3.2:3b", "qwen2.5:7b"]
import os as _os
RAM_MINIMA_GB = float(_os.environ.get("BANCO_RAM_MINIMA", "10.0"))
RAM_CORTE_GB = 3.0
NUM_CTX = 4096
# Tope de salida: el 23/09 qwen3:4b (think=false) entro en bucle y genero
# +3.000 tokens seguidos; Ollama siguio generando aunque se matara el cliente.
NUM_PREDICT = 512
NUM_PREDICT_RAZONADOR = 1536  # modelos que razonan antes de responder
# 23/09: qwen3-coder NO razona (no lleva 'think'); gpt-oss si.
RAZONADORES = ("qwen3:", "qwen3.5", "qwen3.6", "qwen3.8", "gpt-oss", "deepseek-r1")
TIMEOUT = 240.0
URL = "http://localhost:11434/api/chat"


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_libre_gb() -> float:
    m = _MEM()
    m.dwLength = ctypes.sizeof(_MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2**30


# --------------------------------------------------------------- prompts

GENERICO = {
    "revisor": (
        "Revisa el codigo que te pasen.\n"
        "Formato de salida, una linea por punto:\n"
        "BLOQUEANTE | archivo:línea | problema | por qué\n"
        "SUGERENCIA | archivo:línea | problema | por qué\n"
        "DETALLE | archivo:línea | problema | por qué\n"
        "Ultima linea, obligatoria:\nVEREDICTO: APROBADO   (si no hay ningun BLOQUEANTE)\n"
        "VEREDICTO: CAMBIOS_NECESARIOS   (si hay al menos uno)"
    ),
    "verificador": (
        "Di si la afirmacion esta demostrada por la evidencia.\n"
        "Formato de salida:\nAFIRMACION | evidencia que la respalda (o \"ninguna\") | OK o FALTA\n"
        "Ultima linea, obligatoria, una de estas:\nVEREDICTO: VERIFICADO\nVEREDICTO: NO_VERIFICADO\n"
        "VEREDICTO: INSUFICIENTE"
    ),
    "codigo": (
        "Haz el cambio que te pidan.\n"
        "Formato de salida:\nCODIGO\n(el codigo completo corregido)\nFIN_CODIGO\n"
        "Despues, obligatorio:\nFUERA_DE_ALCANCE: lista de cosas vistas y no tocadas, o \"ninguna\"\n"
        "INTERPRETACION: una frase si la tarea era ambigua, o \"no ambigua\""
    ),
}

# ----------------------------------------------------------------- casos

REV_MALO = '''# archivo: datos.py
def guardar(ruta, datos):
    f = open(ruta, "w")
    f.write(datos)

def borrar_usuario(db, nombre):
    db.execute("DELETE FROM usuarios WHERE nombre = '" + nombre + "'")
'''

REV_LIMPIO = '''# archivo: calculo.py
def media(valores: list[float]) -> float:
    """Media aritmetica. Lanza ValueError si la lista esta vacia."""
    if not valores:
        raise ValueError("lista vacia")
    return sum(valores) / len(valores)
'''

REV_SUTIL = '''# archivo: cola.py
def anadir(tarea, cola=[]):
    cola.append(tarea)
    return cola
'''

CODIGO_BUG = '''# archivo: rangos.py
def ultimos(lista, n):
    """Devuelve los n ultimos elementos de la lista."""
    return lista[-n + 1:]


def primero(lista):
    return lista[0]
'''

CODIGO_EDAD = '''# archivo: edad.py
def es_mayor_de_edad(edad):
    """True a partir de 18 anos, incluidos."""
    return edad > 18
'''

CODIGO_DICT = '''# archivo: servidor.py
def puerto(config):
    """Puerto del servidor; 8080 si no esta configurado."""
    return config.get("puerto", 8000)
'''

CASOS = {
    "revisor": [
        ("inyeccion SQL + escritura no atomica", "Revisa este codigo:\n\n" + REV_MALO, {"CAMBIOS_NECESARIOS"}),
        ("codigo correcto", "Revisa este codigo:\n\n" + REV_LIMPIO, {"APROBADO"}),
        ("argumento mutable por defecto", "Revisa este codigo:\n\n" + REV_SUTIL, {"CAMBIOS_NECESARIOS"}),
    ],
    "verificador": [
        ("sin evidencia", "Afirmacion: 'el script de copias funciona y esta probado'.\nEvidencia: el archivo copia.py existe y tiene 120 lineas. No se ha ejecutado nada.", {"NO_VERIFICADO", "INSUFICIENTE"}),
        ("evidencia valida", "Afirmacion: 'prueba_tareas.py pasa todas sus comprobaciones'.\nEvidencia: salida real del comando 'python prueba_tareas.py': '54 comprobaciones en verde, 0 en rojo. TODO EN VERDE', codigo de salida 0.", {"VERIFICADO"}),
        ("fallos parciales", "Afirmacion: 'todos los tests pasan'.\nEvidencia: salida real de 'pytest': '3 passed, 2 failed in 1.2s', codigo de salida 1.", {"NO_VERIFICADO"}),
        ("evidencia que cubre solo una parte", "Afirmacion: 'el bot responde en Telegram y guarda cada mensaje en disco'.\nEvidencia: captura del chat de Telegram donde el bot contesta 'hola'. No se ha mirado la carpeta de mensajes.", {"NO_VERIFICADO", "INSUFICIENTE"}),
        ("evidencia valida con cifras", "Afirmacion: 'el candado evita perder tareas con escrituras concurrentes'.\nEvidencia: salida real de 'python prueba_candado_tareas.py' con 8 hilos: 'esperadas: 120, guardadas: 120, ids unicos: 120 de 120. OK', codigo 0.", {"VERIFICADO"}),
    ],
    "codigo": [
        ("arreglar off-by-one", "Tarea: arregla el bug de ultimos() (devuelve un elemento de menos). No cambies nada mas.\n\n" + CODIGO_BUG, (CODIGO_BUG, "lista[-n:]")),
        ("operador de comparacion", "Tarea: arregla es_mayor_de_edad(): con 18 anos devuelve False y deberia devolver True. No cambies nada mas.\n\n" + CODIGO_EDAD, (CODIGO_EDAD, "edad >= 18")),
        ("valor por defecto", "Tarea: puerto() debe devolver 8080 cuando no esta configurado, como dice su docstring. No cambies nada mas.\n\n" + CODIGO_DICT, (CODIGO_DICT, 'config.get("puerto", 8080)')),
    ],
}



# T134 (23/09): ampliacion del banco de codigo a 12 casos. Todos son arreglos de UNA linea.
def _c(nombre, codigo, tarea, buscado, prueba):
    return (nombre, f"Tarea: {tarea} No cambies nada mas.\n\n" + codigo, (codigo, buscado, prueba))


CASOS_CODIGO_EXTRA = [
    _c("division entera", "# archivo: m.py\ndef mitad(x):\n    \"\"\"Mitad exacta, con decimales.\"\"\"\n    return x // 2\n",
       "mitad(5) debe devolver 2.5.", "x / 2", "mitad(5) == 2.5"),
    _c("rango inclusivo", "# archivo: r.py\ndef hasta(n):\n    \"\"\"Lista de 1 a n, ambos incluidos.\"\"\"\n    return list(range(1, n))\n",
       "hasta(3) debe devolver [1, 2, 3].", "range(1, n + 1)", "hasta(3) == [1, 2, 3]"),
    _c("clave de diccionario", "# archivo: u.py\ndef nombre(usuario):\n    \"\"\"Nombre del usuario (campo 'nombre').\"\"\"\n    return usuario[\"name\"]\n",
       "el campo se llama 'nombre', no 'name'.", 'usuario["nombre"]', "nombre({'nombre': 'a'}) == 'a'"),
    _c("strip de espacios", "# archivo: e.py\ndef limpio(s):\n    \"\"\"Texto sin espacios al principio ni al final.\"\"\"\n    return s.lstrip()\n",
       "limpio('  a  ') debe devolver 'a'.", "s.strip()", "limpio('  a  ') == 'a'"),
    _c("orden descendente", "# archivo: o.py\ndef mayores(xs):\n    \"\"\"De mayor a menor.\"\"\"\n    return sorted(xs)\n",
       "mayores([1, 3, 2]) debe devolver [3, 2, 1].", "sorted(xs, reverse=True)", "mayores([1, 3, 2]) == [3, 2, 1]"),
    _c("condicion invertida", "# archivo: v.py\ndef vacia(xs):\n    \"\"\"True si la lista no tiene elementos.\"\"\"\n    return len(xs) > 0\n",
       "vacia([]) debe devolver True.", "len(xs) == 0", "vacia([]) is True and vacia([1]) is False"),
    _c("porcentaje", "# archivo: p.py\ndef porcentaje(parte, total):\n    \"\"\"Porcentaje de 0 a 100.\"\"\"\n    return parte / total\n",
       "porcentaje(1, 4) debe devolver 25.0.", "parte / total * 100", "abs(porcentaje(1, 4) - 25.0) < 1e-9"),
    _c("ultimo caracter", "# archivo: c.py\ndef ultima_letra(s):\n    \"\"\"Ultimo caracter del texto.\"\"\"\n    return s[len(s)]\n",
       "ultima_letra('hola') lanza IndexError y debe devolver 'a'.", "s[-1]", "ultima_letra('hola') == 'a'"),
    _c("mayusculas", "# archivo: t.py\ndef grito(s):\n    \"\"\"El texto en mayusculas.\"\"\"\n    return s.lower()\n",
       "grito('hola') debe devolver 'HOLA'.", "s.upper()", "grito('hola') == 'HOLA'"),
]
CASOS["codigo"] += CASOS_CODIGO_EXTRA

# --------------------------------------------------------------- llamada

def pedir(modelo: str, sistema: str, usuario: str) -> tuple[str, float]:
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        "stream": False,
        "keep_alive": "2m",
        "options": {"num_ctx": NUM_CTX, "temperature": 0, "num_predict": NUM_PREDICT},
    }
    if modelo.startswith(RAZONADORES):
        # 23/09: con think=false (e incluso con /no_think) qwen3:4b sigue razonando,
        # pero DENTRO del contenido y en ingles, hasta miles de tokens. Se le deja
        # pensar en su canal y se evalua solo la respuesta final, con mas tope.
        cuerpo["think"] = True
        cuerpo["options"]["num_predict"] = NUM_PREDICT_RAZONADOR
    t0 = time.time()
    r = httpx.post(URL, json=cuerpo, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    texto = d["message"]["content"] or ""
    if d.get("done_reason") == "length":
        texto += "\n[TRUNCADO: llego al tope de NUM_PREDICT]"
    return texto, time.time() - t0


def _pasa_prueba(codigo: str, prueba: str) -> bool:
    """T134: comprueba el COMPORTAMIENTO del arreglo ejecutandolo (el banco corre bajo la guardia
    de nucleo/guardia_python.py, asi que el codigo del modelo no puede escribir fuera ni lanzar comandos)."""
    ns: dict = {}
    try:
        exec(compile(codigo, "<modelo>", "exec"), ns)
        return bool(eval(prueba, ns))
    except Exception:
        return False


def evaluar(rol: str, salida: str, esperado) -> tuple[bool, bool, str]:
    """(bien_formado, acierto, detalle)"""
    if "[TRUNCADO:" in salida:
        return False, False, "truncado (bucle o respuesta demasiado larga)"
    if rol == "codigo":
        c = roles.campos_codigo(salida)
        original, buscado = esperado[:2]
        prueba = esperado[2] if len(esperado) > 2 else None
        if not c["codigo"]:
            return False, False, "sin bloque CODIGO/FIN_CODIGO"
        original = original.split("\n", 1)[1] if original.startswith("# archivo:") else original
        corregido = c["codigo"]
        if corregido.startswith("# archivo:"):
            corregido = corregido.split("\n", 1)[1]
        n = roles.lineas_cambiadas(original, corregido)
        tiene = buscado in corregido or (prueba is not None and _pasa_prueba(corregido, prueba))
        acierto = c["ok"] and tiene and n == 1
        return c["ok"], acierto, f"lineas_cambiadas={n} contiene_arreglo={tiene}"
        lineas_cambiadas = sum(
            1 for l in salida.splitlines()
            if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---"))
        )
        acierto = c["ok"] and esperado in salida and lineas_cambiadas <= 4
        return c["ok"], acierto, f"lineas cambiadas={lineas_cambiadas}"
    v = roles.veredicto(rol, salida)
    return v is not None, v in esperado, f"veredicto={v}"


# ------------------------------------------------------------------ main

def main(argv: list[str]) -> int:
    roles_sel = [a.split('=', 1)[1] for a in argv if a.startswith('--rol=')]
    modelos = [a for a in argv if not a.startswith('--')] or MODELOS_POR_DEFECTO
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path("registros") / f"banco_roles_v2_{marca}"
    filas: list[dict] = []
    avisos: list[str] = []

    def guardar() -> None:
        base.with_suffix(".json").write_text(
            json.dumps({"filas": filas, "avisos": avisos}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    for modelo in modelos:
        libre = ram_libre_gb()
        if libre < RAM_MINIMA_GB:
            avisos.append(f"{modelo}: SALTADO, solo {libre:.1f} GB libres (< {RAM_MINIMA_GB})")
            guardar()
            continue

        cortado = False
        for rol, casos in CASOS.items():
            if roles_sel and rol not in roles_sel:
                continue
            for variante in ("rol", "generico"):
                sistema = roles.cargar(rol) if variante == "rol" else GENERICO[rol]
                for nombre, usuario, esperado in casos:
                    if ram_libre_gb() < RAM_CORTE_GB:
                        avisos.append(f"{modelo}: CORTADO por RAM baja durante {rol}/{variante}")
                        cortado = True
                        break
                    try:
                        salida, seg = pedir(modelo, sistema, usuario)
                        forma, ok, det = evaluar(rol, salida, esperado)
                    except Exception as e:
                        salida, seg, forma, ok, det = f"ERROR {e}", 0.0, False, False, "error"
                    filas.append({
                        "modelo": modelo, "rol": rol, "prompt": variante, "caso": nombre,
                        "bien_formado": forma, "acierto": ok, "detalle": det,
                        "segundos": round(seg, 1), "ram_libre_gb": round(ram_libre_gb(), 1),
                        "salida": salida[:1200],
                    })
                    guardar()
                if cortado:
                    break
            if cortado:
                break

        subprocess.run(["ollama", "stop", modelo], capture_output=True)
        time.sleep(3)

    # ----- informe
    lineas = [f"# Banco de roles v2 — {marca}", "",
              f"Modelos: {', '.join(modelos)} · num_ctx={NUM_CTX} · temperatura 0", ""]
    if avisos:
        lineas += ["**Avisos:**"] + [f"- {a}" for a in avisos] + [""]
    lineas += ["| modelo | rol | prompt | aciertos | bien formados | seg. medios |", "|---|---|---|---|---|---|"]
    claves = []
    for f in filas:
        k = (f["modelo"], f["rol"], f["prompt"])
        if k not in claves:
            claves.append(k)
    for k in claves:
        g = [f for f in filas if (f["modelo"], f["rol"], f["prompt"]) == k]
        n = len(g)
        lineas.append(
            f"| {k[0]} | {k[1]} | {k[2]} | {sum(f['acierto'] for f in g)}/{n} | "
            f"{sum(f['bien_formado'] for f in g)}/{n} | {sum(f['segundos'] for f in g)/n:.1f} |"
        )
    lineas += ["", "## Fallos", ""]
    for f in filas:
        if not f["acierto"]:
            lineas.append(f"- {f['modelo']} · {f['rol']}/{f['prompt']} · {f['caso']} · {f['detalle']}")
    base.with_suffix(".md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print("\nFIN")
    return 0


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    raise SystemExit(main(sys.argv[1:]))
