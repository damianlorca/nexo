# -*- coding: utf-8 -*-
"""Mapa de ideas por TEMA (Damian 23/09): antes de trabajar en un tema, ver TODO lo relacionado.

Vista legible: contexto/proyectos/nexo/mapa-ideas-nexo.md. Aqui la parte de maquina: que tareas y
que herramientas del catalogo pertenecen a cada tema. aplicar() pone etiquetas 'tema:<x>' en las
tareas y 'categoria' en el catalogo; tema(x) lista todo lo de un tema con su estado.

Uso: .venv\\Scripts\\python.exe -m nucleo.mapa <tema>      (sin tema: lista los temas)
     .venv\\Scripts\\python.exe -m nucleo.mapa --aplicar
"""
from __future__ import annotations

import sys

TEMAS = {
    "modelos_proveedores_roles": {
        "titulo": "A. Modelos, proveedores y roles de agentes",
        "tareas": "T134 T051 T085 T005 T052 T057 T094 T059 T121 T122 T147 T151 T136 T132 T049 T101 T096 T097 T102 T152 T130",
        "catalogo": "H041 H002 H043 H055 H037 H020 H021 H056 H057",
        "ver_tambien": ["orquestacion", "ahorro_claude_dev"],
    },
    "orquestacion": {
        "titulo": "B. Orquestacion: Router, turno, pipeline multi-IA, rutinas",
        "tareas": "T079 T053 T054 T062 T063 T065 T082 T119 T142 T143",
        "catalogo": "H010 H074 H038 H024 H006",
        "ver_tambien": ["modelos_proveedores_roles", "memoria_contexto"],
    },
    "memoria_contexto": {
        "titulo": "C. Memoria y contexto",
        "tareas": "T144 T083 T033 T064",
        "catalogo": "H039 H040 H023 H003 H025 H026 H027 H028 H008 H029 H022 H036",
        "ver_tambien": ["orquestacion"],
    },
    "ahorro_claude_dev": {
        "titulo": "D. Ahorro de Claude y herramientas de desarrollo",
        "tareas": "T029 T135 T139 T124 T127 T078",
        "catalogo": "H031 H034 H035 H033 H012 H030 H032 H001 H068 H044",
        "ver_tambien": ["modelos_proveedores_roles"],
    },
    "seguridad_permisos": {
        "titulo": "E. Seguridad y permisos",
        "tareas": "T091 T024 T077 T145 T048 T123 T148 T016",
        "catalogo": "H007 H063 H049 H076 H044",
        "ver_tambien": ["interfaz_app_voz"],
    },
    "interfaz_app_voz": {
        "titulo": "F. Interfaz, app, voz y canales",
        "tareas": "T140 T116 T117 T103 T107 T025 T027 T149 T055 T075 T099 T150 T146",
        "catalogo": "H011 H013 H014 H015 H017 H065 H066 H050 H053 H005",
        "ver_tambien": ["orquestacion", "seguridad_permisos", "memoria_contexto"],
    },
    "navegador_pc": {
        "titulo": "G. Navegador y control del PC",
        "tareas": "T147 T066 T076 T056 T027",
        "catalogo": "H009 H045 H051 H061",
        "ver_tambien": ["modelos_proveedores_roles"],
    },
    "infraestructura": {
        "titulo": "H. Infraestructura",
        "tareas": "T037 T138 T114 T049 T132",
        "catalogo": "",
        "ver_tambien": [],
    },
    "contenido_personal": {
        "titulo": "I. Contenido, negocio y personal",
        "tareas": "T092 T129 T007 T013 T014 T017 T018",
        "catalogo": "H042 H047 H016 H018 H019 H054 H004",
        "ver_tambien": [],
    },
    "recursos_por_identificar": {
        "titulo": "J-K. Recursos y por identificar",
        "tareas": "T108 T109 T110 T133",
        "catalogo": "H059 H060 H062 H058 H064 H067 H069 H070 H071 H072 H073 H075",
        "ver_tambien": ["modelos_proveedores_roles"],
    },
}


def tema(nombre: str) -> str:
    from nucleo import catalogo as C
    from nucleo import tareas as T
    info = TEMAS[nombre]
    lin = [f"== {info['titulo']} ==", "Tareas:"]
    for tid in info["tareas"].split():
        t = T.buscar(tid)
        if t:
            lin.append(f"  {tid} [{t['estado']}] {t['titulo'][:90]}")
    lin.append("Catalogo:")
    datos = C.cargar()
    for hid in info["catalogo"].split():
        x = C.buscar(datos, hid)
        if x:
            lin.append(f"  {hid} [{x['veredicto']}/{x['auditado']}] {x['nombre']}")
    if info["ver_tambien"]:
        lin.append("Ver tambien: " + ", ".join(info["ver_tambien"]))
    lin.append("Detalle legible: contexto/proyectos/nexo/mapa-ideas-nexo.md")
    return "\n".join(lin)


def aplicar() -> tuple[int, int]:
    from nucleo import catalogo as C
    from nucleo import tareas as T
    nt = nc = 0
    for nombre, info in TEMAS.items():
        for tid in info["tareas"].split():
            t = T.buscar(tid)
            if t and f"tema:{nombre}" not in (t.get("etiquetas") or []):
                T.actualizar(tid, etiquetas=list(t.get("etiquetas") or []) + [f"tema:{nombre}"])
                nt += 1
        for hid in info["catalogo"].split():
            try:
                C.poner(hid, categoria=nombre)
                nc += 1
            except KeyError:
                pass
    return nt, nc


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)  # --help sin ejecutar nada (incidente 05/10)
    from nucleo import consola
    consola.preparar()   # consola cp1252 de Windows: '?' en lo que no cabe, tildes intactas
    a = sys.argv[1:]
    if not a:
        print("Temas:", ", ".join(TEMAS))
    elif a[0] == "--aplicar":
        print("etiquetas de tema puestas (tareas, catalogo):", aplicar())
    else:
        print(tema(a[0]))
