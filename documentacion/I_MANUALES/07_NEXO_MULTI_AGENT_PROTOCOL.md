# I.7 NEXO_MULTI_AGENT_PROTOCOL

## Por qué no hace falta infraestructura nueva

El patrón ya existe y está probado en producción: `canal/buzon.py` (archivos JSON + `escribir_atomico` + candado) para el agente↔móvil. Las 4 IAs consultadas en la Fase 3 (Qwen, Gemini, ChatGPT, y el análisis propio de Claude) coincidieron en aplicar el mismo patrón entre proveedores — ver `G_SINTESIS_MULTI_IA.md` caso D.

## Estructura de mensaje propuesta (campos pedidos por la especificación maestra, confirmados por Qwen literalmente)

```json
{
  "sender": "qwen | gemini | chatgpt | claude",
  "receiver": "qwen | gemini | chatgpt | claude",
  "task_id": "identificador de la tarea (T0xx o ad-hoc)",
  "message_type": "resumen | investigacion | redaccion | revision | ...",
  "payload": "contenido del mensaje",
  "context": "contexto adicional necesario para el siguiente paso",
  "priority": "prioridad",
  "timestamp": "cuándo se escribió",
  "status": "pendiente | en_proceso | hecho | error",
  "result": "resultado, si lo hay",
  "error": "error, si lo hay"
}
```

## Mecanismo propuesto

Carpeta `canal/entre_ias/`, un archivo por mensaje, mismo patrón que `canal/salida/`: quien produce escribe con `escribir_atomico`, quien consume lee y marca como procesado (renombrar, igual que `buzon.mensajes_nuevos()` hace con `.leido`). Candado (`nucleo/candado.py`) si dos IAs pudieran escribir en el mismo sitio a la vez (poco probable en un flujo secuencial, pero barato de añadir).

## Límites explícitos (para no romper las reglas ya fijadas)

- Nada de bucles desatendidos entre Gemini/ChatGPT: cada salto de la cadena a un proveedor vía navegador cuenta contra el volumen bajo y espaciado ya acordado.
- Claude solo participa en la cadena disparando una Rutina completa (no hay una llamada "ligera" de Claude): el último eslabón que involucre a Claude debe ser deliberado, no automático por defecto.
- Trazabilidad obligatoria: todo mensaje se queda en disco (no se borra), para poder reconstruir qué pasó si algo falla a mitad de la cadena.

## No implementar todavía

Diseño de Fase 5. Ver `J_ROADMAP_PRIORIZADO.md` P1.2.
