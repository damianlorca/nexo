# FASE 4 — G. Proyectos y conversaciones: diseño estable, releído en capas

## Sin cambios de fondo respecto a FASE3_F

La jerarquía `PROVEEDOR → PROYECTO → CHAT → TAREA → CONTEXTO → RESULTADO`, los campos del "proyecto de IA", el patrón `ConversationManager`, y el hallazgo de navegación por URL directa — todo se mantiene tal cual quedó diseñado en FASE3_F. Damián lo repite en este mensaje casi punto por punto, sin pedir ningún cambio de contenido, así que esta sección no repite ese diseño — se limita a ubicarlo en el modelo de capas de FASE4_A, que es lo único que añade valor nuevo aquí.

## Dónde vive esto en la arquitectura en capas

- **Capa A (Runtime):** decide qué proyecto/chat corresponde a una tarea, mantiene el índice local (`proyectos_ia.json`, ya propuesto en FASE3_F) — es lógica de orquestación, no de acceso al proveedor.
- **Capa C (Tools):** el `ConversationManager` y sus adaptadores (crear/seleccionar/verificar conversación) son una TOOL — igual que `manos/archivos.py` es la tool de "tocar archivos", esto es la tool de "tocar una conversación web". No es el proveedor en sí (capa D): el proveedor Gemini/ChatGPT es "a quién se le pregunta", esta tool es "cómo se le pregunta en el lugar correcto".
- **Capa D (Proveedores):** cada proveedor declara, en su `PerfilProveedor` (FASE4_F), si soporta el concepto de proyecto/carpeta (ChatGPT sí, de forma más madura; Gemini más limitado, según la experiencia ya documentada) — el Runtime usa ese dato para decidir si vale la pena organizar por proyecto en ese proveedor concreto o si basta con conversaciones sueltas.

## Por qué esta relectura importa

Evita el mismo error que ya se señaló en FASE4_A para `navegador.py` en general: sin esta separación, sería fácil que "gestionar proyectos de Gemini" se programara como lógica pegada al proveedor Gemini, en vez de como una tool genérica de "gestión de conversación" que cualquier proveedor basado en navegador puede reutilizar (Gemini y ChatGPT comparten casi toda la misma tool hoy, con un adaptador fino por encima — así debe seguir siendo cuando se implemente).

## Sin implementación en esta fase

Igual que el resto — este documento es una relectura organizativa, no un cambio de diseño. La implementación sigue en el mismo lugar del roadmap que ya tenía en FASE3_N (extensión de `navegador.py`, adelantada respecto al control visual genérico).
