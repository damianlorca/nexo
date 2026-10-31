# FASE 2 — L. Dependencias entre piezas y orden recomendado de implementación

Disciplina obligatoria para cada paso, sin excepción: **UNA IMPLEMENTACIÓN → PRUEBA REAL → VERIFICACIÓN → DOCUMENTACIÓN → SIGUIENTE IMPLEMENTACIÓN.** Nada de lo que sigue se implementa en esta misma tarea — es el orden recomendado para cuando Damián autorice retomar implementación.

## Mapa de dependencias (resumen)

- **Seguridad ampliada (J)** no depende de nada nuevo — puede (y debería) ir primero, sobre el código ya existente.
- **Observabilidad (F)** no depende de nada nuevo tampoco — puede ir en paralelo con J, es la otra pieza "barata e independiente".
- **Papel ampliado de Qwen (A)** depende de tener ya observabilidad (F) mínima, para poder medir si el nuevo trabajo delegado a Qwen realmente reduce lo que antes hacía Claude.
- **Model Router (B)** depende de A (necesita saber qué puede resolver Qwen) y se beneficia de tener F (para medir su propio efecto en el consumo).
- **Gestión de proyectos/chats multi-IA (C)** depende de B (el router decide cuándo usar Gemini/ChatGPT; C decide cómo).
- **Estrategia de Claude (E)** es independiente en gran parte (ya resuelta como documento), pero la pieza pendiente real (D/E como red de recuperación) depende de tener control visual.
- **Control visual (D)** depende de J (permisos ampliados a acciones visuales) — no debe implementarse antes.
- **Autonomía incremental (I)** depende de A, B, F y J todos a la vez — es, por diseño, de las últimas piezas.
- **Turno de noche (H)** no es una implementación nueva — es una decisión operativa (pausar/no pausar) independiente del resto, pendiente de confirmación de Damián.

## Orden recomendado

1. **Seguridad: cerrar L1 (`ejecutar_python`) y REQ-070** — sin autonomía nueva todavía, corrige deuda ya conocida. Prueba real: intentar los mismos casos que originalmente demostraron el bypass/lectura sin restricción, confirmar que ahora se bloquean.
2. **Observabilidad mínima (F): `memoria/estado_actual.json` + comando `/estado` en Telegram** — pieza barata, autocontenida, y útil de inmediato incluso sin nada más del roadmap.
3. **Ampliar el papel de Qwen (A): resumen de notas largas + verificación mecánica bajo demanda** — el candidato de menor riesgo (resumir/verificar, nunca decidir), medible de inmediato con la observabilidad ya en pie.
4. **Vigilante ligero de bucles con Qwen (A+F)** — una vez F y el Qwen ampliado existen, es una extensión natural de ambos.
5. **Model Router (B)** — con Qwen ya haciendo más y con observabilidad para medir el efecto, tiene sentido formalizar la clasificación tarea→proveedor→esfuerzo.
6. **Políticas de economía de uso (G)** — se aplican sobre el Router ya construido, no antes (no hay nada que optimizar todavía sin él).
7. **Gestión de proyectos/chats (C)** — una vez el Router decide cuándo usar Gemini/ChatGPT, formalizar cómo se organiza esa conversación.
8. **Permisos ampliados a visual/multi-agente/origen-de-orden (J, la parte que falta tras el paso 1)** — antes de tocar control visual.
9. **Control visual (D)** — al final, con seguridad y observabilidad ya firmes debajo.
10. **Autonomía incremental (I)** — última pieza, cuando todo lo anterior ya está probado por separado.

**Turno de noche (H):** decisión operativa a tomar ahora, no una implementación — no ocupa un puesto en esta secuencia.

## Riesgo de saltarse el orden

Cualquier atajo que implemente autonomía (I) o control visual (D) antes de cerrar seguridad (paso 1) o sin observabilidad (paso 2) reproduce exactamente el patrón que generó L1 y REQ-070 en primer lugar: funcionalidad primero, control después. Es el riesgo técnico principal de todo este roadmap (ver también sección T del índice).
