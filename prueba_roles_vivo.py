# -*- coding: utf-8 -*-
"""Prueba EN VIVO de roles/ con UN modelo pequeno (qwen2.5:7b), con guardas
de RAM (leccion del incidente T100 del 23/09): comprueba memoria libre antes,
un solo modelo, keep_alive corto y 'ollama stop' al terminar."""
import ctypes
import subprocess
import time
from pathlib import Path

from openai import OpenAI

import roles


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


MODELO = "qwen2.5:7b"
SALIDA = Path("registros/prueba_roles_vivo.txt")
lineas = []


def log(s):
    lineas.append(s)
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


libre = ram_libre_gb()
log(f"RAM libre al empezar: {libre:.1f} GB")
if libre < 10:
    log("ABORTADO: menos de 10 GB libres")
    raise SystemExit(1)

cli = OpenAI(base_url="http://localhost:11434/v1", api_key="local", timeout=300, max_retries=0)

CODIGO_MALO = '''def guardar(ruta, datos):
    f = open(ruta, "w")
    f.write(datos)
    # si falla a mitad, el archivo queda truncado

def borrar_usuario(db, nombre):
    db.execute("DELETE FROM usuarios WHERE nombre = '" + nombre + "'")
'''

CASOS = [
    ("revisor", "Revisa este codigo Python:\n\n" + CODIGO_MALO, "CAMBIOS_NECESARIOS"),
    (
        "verificador",
        "Afirmacion: 'el script de copias de seguridad funciona y esta probado'.\n"
        "Evidencia disponible: el archivo copia.py existe y tiene 120 lineas. "
        "No se ha ejecutado ningun comando ni test.",
        "NO_VERIFICADO",
    ),
    (
        "verificador",
        "Afirmacion: 'prueba_roles.py pasa todos sus casos'.\n"
        "Evidencia disponible: salida real del comando 'python prueba_roles.py': "
        "'CODIGO: 0 ... TODO VALE: codigo=967 car., revisor=1038 car., verificador=1159 car.'",
        "VERIFICADO",
    ),
    (
        "verificador",
        "Afirmacion: 'todos los tests pasan y el modulo esta listo para produccion'.\n"
        "Evidencia disponible: salida real de 'pytest': '3 passed, 2 failed in 1.2s', codigo de salida 1.",
        "NO_VERIFICADO",
    ),
]

aciertos = 0
for rol, tarea, esperado in CASOS:
    t0 = time.time()
    r = cli.chat.completions.create(
        model=MODELO,
        messages=[{"role": "system", "content": roles.cargar(rol)}, {"role": "user", "content": tarea}],
        temperature=0,
        extra_body={"keep_alive": "2m"},
    )
    txt = r.choices[0].message.content or ""
    v = roles.veredicto(rol, txt)
    ok = v == esperado
    aciertos += ok
    log(f"\n=== {rol} | esperado={esperado} | obtenido={v} | {'OK' if ok else 'FALLO'} | {time.time()-t0:.1f}s | RAM libre {ram_libre_gb():.1f} GB")
    log(txt.strip()[:1500])

log(f"\nRESULTADO: {aciertos}/{len(CASOS)} veredictos correctos y bien formados")
subprocess.run(["ollama", "stop", MODELO], capture_output=True)
log(f"ollama stop {MODELO} hecho. RAM libre al acabar: {ram_libre_gb():.1f} GB")
log("FIN")
