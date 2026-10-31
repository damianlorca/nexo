"""27/09/2026: evaluar modelos gratis de NVIDIA (lista de Damian) + ventana de Chrome que salta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nucleo import tareas as T  # noqa: E402

ev = T.anadir(
    "Evaluar los modelos gratis de NVIDIA y ampliar la lista blanca por roles",
    detalle=("Lista de Damian en documentacion/proveedores/NVIDIA_MODELOS_GRATIS.md. Hoy la lista blanca de T227 solo tiene "
             "gpt-oss-20b/120b (misma familia que Groq, latencia de 11 s a mas de 120 s). Hacer: (1) comprobar con /models que "
             "cada candidato existe y es gratis; (2) mini-banco: 3-5 casos por rol (revisor de borrador, autor de investigacion, "
             "clasificador rapido, codigo) midiendo latencia, calidad y errores; (3) priorizar revisores de OTRA FAMILIA "
             "(nemotron, deepseek, glm, mistral-nemotron, gemma, kimi) para tener revision independiente sin gastar ChatGPT/Gemini; "
             "(4) apuntar como candidatos: nemotron-3-embed-1b para RAG/memoria (T181/T144), clasificadores de seguridad contra "
             "inyeccion (T158), vision (T027), voz (T025/T159); (5) proponer la lista blanca por rol; Damian decide. Solo gratis."),
    importancia=5, urgencia=4, dificultad=2, coste=1, depende="ia",
    etiquetas=["cat:investigacion", "prov:claude", "tema:modelos_proveedores_roles", "origen:damian_chat"])

ven = T.anadir(
    "BUG: la ventana del Chrome de NEXO vuelve a saltar al frente despues de minimizarla",
    detalle=("Damian 27/09: cuando NEXO trabaja con Gemini/ChatGPT la ventana aparece en medio de la pantalla; la primera vez no "
             "le importa, pero si la minimiza no debe volver a salir. Revisar navegador.py y los scripts: bring_to_front(), "
             "paginas o ventanas nuevas, foco. Opciones: no traer al frente; reutilizar la pestana; lanzar Chrome con "
             "--disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-background-timer-throttling "
             "para que trabaje igual minimizado (comprobar que Gemini/ChatGPT siguen respondiendo y que Pensar se activa con la "
             "ventana minimizada). Prueba real: minimizar y lanzar una pregunta; la ventana no debe reaparecer."),
    importancia=4, urgencia=4, dificultad=2, coste=1, depende="ia",
    etiquetas=["cat:codigo", "prov:claude", "tema:modelos_proveedores_roles", "bug", "correccion_errores"])

T.anotar("T201", "27/09: en el catalogo gratis de NVIDIA hay 'muse-glimmer-30b' (Meta, multimodal con razonamiento y herramientas). "
                 "Comprobar si es el 'Muse' que queria Damian.")
T.anotar("T227", f"27/09: ampliar la lista blanca segun la evaluacion {ev['id']} (lista completa en documentacion/proveedores/NVIDIA_MODELOS_GRATIS.md).")
print(ev["id"], ven["id"])
