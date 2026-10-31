"""Correccion puntual (26/09/2026) de la clasificacion de ordenes de Damian.

Revision pedida por Damian: comprobar que sus ordenes estan bien
clasificadas y en tareas. Usa la API de nucleo.tareas (con candado).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402


def etiquetas(tid, quitar=(), poner=()):
    t = T.buscar(tid)
    et = [e for e in (t.get("etiquetas") or []) if not any(e.startswith(q) for q in quitar)]
    for p in poner:
        if p not in et:
            et.append(p)
    return et


# T170 -> tarea para Claude, idea del bloque de monetizacion (T092)
T.actualizar("T170", depende="ia",
             etiquetas=etiquetas("T170", ("cat:", "prov:"), ("cat:monetizacion", "prov:claude", "bloque:T092")))
T.anotar("T170", "26/09: pasada a tarea para Claude (orden T171). Es una idea del bloque de monetizacion T092.")
T.anotar("T092", "26/09: idea nueva en T170: carteles impresos en 3D con chip NFC para resenas de Google / web de empresas.")
T.completar("T171", "Aplicado el 26/09: T170 pasa a Claude. Era una orden directa que no se ejecuto y acabo como tarea (ver T186).")

# T172 (API gratis de NVIDIA) -> mismo trabajo que T162 (proveedores API OpenAI-compatibles)
T.actualizar("T172", etiquetas=etiquetas("T172", ("tema:",), ("tema:modelos_proveedores_roles", "junto_a:T162")))
T.anotar("T172", "26/09: se hace junto a T162. build.nvidia.com ofrece API compatible con OpenAI, mismo patron que Groq/OpenRouter.")
T.anotar("T162", "26/09: anadir tambien NVIDIA (build.nvidia.com, orden T172) como proveedor OpenAI-compatible.")

# T185 (prueba de push) -> prueba del hito movil, depende de Damian
T.actualizar("T185", depende="damian",
             etiquetas=etiquetas("T185", ("cat:", "prov:", "escalado:"), ("cat:prueba", "prov:nexo", "tema:interfaz_app_voz")))
T.anotar("T185", "26/09: no se pudo enviar porque no hay ninguna suscripcion (memoria/push vacio). "
                 "Falta: movil -> Ajustes -> Activar notificaciones -> Enviar prueba. Era una orden instantanea, no una tarea de codigo.")

# T173: respuesta con evidencia
T.anotar("T173", "26/09: hoy NO. Las ordenes web se guardan como tareas, pero nadie las ejecuta ni avisa a Claude solo: "
                 "T185 llevaba 21 h sin hacerse y T171 nunca se aplico. Lo resuelven T140 (app de ordenes), T079 (turno sin Claude) y T186.")

nueva = T.anadir(
    "Ordenes instantaneas mal clasificadas: acciones directas acaban como tareas de Claude",
    detalle=("Evidencia 26/09: 'cambia T170 a tarea para Claude' (T171) y 'mandame un push en 5 min' (T185) "
             "se guardaron como tareas cat:codigo/prov:claude en vez de ejecutarse. El triaje de ordenes debe "
             "distinguir ACCION DIRECTA (editar una tarea, mandar un push, programar un aviso) de TAREA, "
             "ejecutar las acciones con las herramientas de NEXO y confirmar al usuario. Ademas, tras el 401 "
             "del 25/09 las ordenes del movil se perdieron sin avisar: la web debe decir si una orden no se guardo."),
    importancia=5, urgencia=4, dificultad=3, coste=2, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:interfaz_app_voz", "app-ordenes"],
)
print("nueva:", nueva["id"])
for tid in ("T170", "T171", "T172", "T173", "T185", nueva["id"]):
    t = T.buscar(tid)
    print(tid, t["estado"], t.get("depende"), "/".join(t.get("etiquetas") or []))
