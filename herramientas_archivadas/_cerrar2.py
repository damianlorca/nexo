"""Segunda actualizacion del estado del turno del 12/09, ya con T041 cerrada."""

from nucleo import estado as es

with es.bloqueo(es.CANDADO):
    e = es.cargar()

    # Ya no hace falta avisar de T041 como pendiente: esta hecha.
    e.siguiente_turno = [
        linea for linea in e.siguiente_turno
        if not linea.startswith("T041 es lo unico que queda de imagenes")
    ]

    e.siguiente_turno.insert(
        2,
        "IMAGENES, de cara al movil: /imagen <texto> ya funciona en el bot (T041, cerrada). "
        "Si Damian dice que no le responde, lo primero es mirar si el bot lleva el codigo "
        "nuevo: se reinicio a las 02:01 del 12/09.",
    )

    e.guardar()

es.actualizar_campos(
    ultima_accion=(
        "Turno de noche del 12/09 (01:01-02:05): dejar las imagenes funcionando de verdad "
        "y ademas pedibles desde el movil."
    ),
)

es.anadir_hecho(
    "El bot corre como pythonw.exe, NO como python.exe. Buscarlo con "
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" no lo encuentra y parece "
    "que esta muerto cuando esta perfectamente vivo (susto del 12/09 02:00). El vigilante "
    "si hace su trabajo: matado el bot a proposito, lo relanzo solo en 10 s."
)

es.anadir_hecho(
    "T041 (12/09, cerrada): /imagen <texto> en el bot de Telegram. Contesta al momento y "
    "manda la foto en un hilo aparte cuando esta (~30 s). Si la generacion falla, avisa por "
    "el chat sin tumbar el bot. Pruebas: prueba_imagen_bot.py (sin GPU ni Telegram). "
    "Commits c494a2b (generacion) y 3b77bd1 (comando)."
)

final = es.cargar()

print("hechos:", len(final.hechos), "| siguiente_turno:", len(final.siguiente_turno))
print("actualizado:", final.actualizado)
