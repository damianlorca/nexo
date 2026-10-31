"""27/09/2026: peticiones de Damian sobre proveedores y conversaciones + defectos hallados por Code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

falso = T.anadir(
    "BUG: falso OK del navegador (ChatGPT devuelve texto de otra conversacion) + candado exclusivo del Chrome de NEXO",
    detalle=("Prueba real de Code 27/09: ChatGPT no llego a publicar la pregunta y el metodo de respaldo devolvio OK con "
             "texto viejo de la pagina ('Revision de groq', de otra ejecucion). Coincidio con otra sesion usando el mismo "
             "Chrome (la investigacion T177 de 13:12-13:20): dos procesos se pisaron. Arreglo: (1) candado exclusivo del "
             "Chrome NEXO (un solo proceso cada vez; el segundo espera o falla con mensaje claro); (2) la respuesta solo vale "
             "si el ultimo mensaje del usuario en la conversacion es EXACTAMENTE nuestro prompt y la respuesta es posterior; "
             "si no, FALLO, nunca OK; (3) el metodo de respaldo no puede devolver OK por su cuenta; (4) lectura DOM de "
             "ChatGPT arreglada (hoy falla y el respaldo tarda ~3 min); (5) tests con DOM grabado. Mismo modulo que T188: "
             "se hacen en la misma sesion."),
    importancia=5, urgencia=5, dificultad=3, coste=2, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:modelos_proveedores_roles", "bug", "correccion_errores"])

rot = T.anadir(
    "Rotacion de proveedores y evaluacion cruzada: todos prueban a ir primero y todos revisan a todos",
    detalle=("Damian 27/09: hoy siempre va primero el mismo y revisa siempre el mismo, asi no sabemos quien es mejor en que. "
             "Construir: (1) modo 'evaluacion' del Router/trabajo.py: el autor rota entre los proveedores activos (ChatGPT, "
             "Gemini, Groq, Qwen local, los que haya) y cada borrador lo revisan TODOS los demas; (2) registro por "
             "(tipo de tarea, autor, revisor): gravedad, fallos reales encontrados, veredicto final de Claude, tiempo, errores/"
             "bloqueos, modo usado (Pensar/Pro); (3) informe tras N tareas por tipo, con propuesta de orden predeterminado por "
             "tipo de tarea; Damian decide el orden. Requisitos previos: T188 (modo) y el bug del falso OK, o los datos saldran "
             "sucios. Coste: mas cuota web; limitar a N tareas por dia y respetar enfriamientos."),
    importancia=4, urgencia=3, dificultad=3, coste=3, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:modelos_proveedores_roles"])

ctrl = T.anadir(
    "App: activar/desactivar proveedores (general y por tarea) y ordenar el orden de llamada",
    detalle=("Damian 27/09: capacidad nueva en la app. (1) Pantalla Ajustes > Proveedores: interruptor por proveedor "
             "(ChatGPT, Gemini API, Gemini web, Groq, Qwen/Ollama, Claude...) y lista ordenable del orden predeterminado de "
             "llamada; (2) en la ficha de una tarea: proveedores permitidos/excluidos y orden propio para esa tarea; (3) si la "
             "tarea exige un proveedor concreto, se llama directamente a ese; si no, se usa el orden (de la tarea o el general); "
             "(4) guardado en memoria/proveedores_control.json, el Router y trabajo.py lo leen en cada llamada; CSRF y registro "
             "de cambios; (5) tambien /proveedores en Telegram (ver/activar/desactivar); (6) tests: proveedor desactivado nunca "
             "se llama; orden respetado; tarea con proveedor fijo va directa."),
    importancia=4, urgencia=3, dificultad=3, coste=2, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:interfaz_app_voz", "app-ordenes"])

vig = T.anadir(
    "BUG: interfaz/vigia.py matar_anotada() mata sin /T y deja el uvicorn vivo con el puerto ocupado",
    detalle="Hallado por Code 27/09 en la revision del paso 4. Usar taskkill /PID <pid> /T tras comprobar la linea de comando exacta; test.",
    importancia=3, urgencia=3, dificultad=1, coste=1, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:interfaz_app_voz", "bug", "correccion_errores"])

T.anotar("T183", "27/09 Damian: el OK absoluto exige MISMA conversacion con el mismo tema, iterando hasta una respuesta "
                 "excelente (antes el fallo era no cambiar nunca de chat; ahora abre chats nuevos de mas). Regla: una conversacion "
                 "por tarea/tema, su URL guardada en la tarea para retomarla; conversacion nueva solo para tema nuevo o si la "
                 "anterior se estropea; tope de iteraciones y criterio de 'excelente' explicito.")
T.anotar("T188", f"27/09: se hace en la misma sesion que {falso['id']} (mismo modulo del navegador).")
print(falso["id"], rot["id"], ctrl["id"], vig["id"])
