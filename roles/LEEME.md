# roles/ — prompts de rol para las IAs de Nexo

| Rol | Archivo | Adaptado de (agency-agents) | Salida verificable |
|---|---|---|---|
| Revisor de código | `revisor.md` | `engineering/engineering-code-reviewer.md` | `VEREDICTO: APROBADO / CAMBIOS_NECESARIOS` |
| Verificador (Principio de Verdad) | `verificador.md` | `testing/testing-reality-checker.md` + `testing/testing-evidence-collector.md` (adaptados de capturas web a evidencia de comandos/tests) | `VEREDICTO: VERIFICADO / NO_VERIFICADO / INSUFICIENTE` |
| Programador de cambio mínimo | `codigo.md` | `engineering/engineering-minimal-change-engineer.md` | diff + `FUERA_DE_ALCANCE:` + `INTERPRETACION:` |

Uso: `import roles; roles.cargar("revisor")` da el prompt de sistema; `roles.veredicto("revisor", salida)` extrae el veredicto (None si falta o es inválido — nunca cuenta como aprobado). Prueba: `prueba_roles.py`.

`codigo.md` incluye la escalera de solución mínima (T256, aprobada 28/09 sobre las reglas de DietrichGebert/ponytail, MIT, adaptadas sin plugin ni hooks): hace falta → ya existe → estándar → nativo/instalado → mínimo nuevo, sin recortar nunca validación en fronteras de confianza, seguridad, prevención de pérdida de datos ni tests (T257, fundida en T256). Es **solo para modelos fuertes** (Claude, ChatGPT, Gemini, gpt-oss): el propio banco de Ponytail mide que la escalera transfiere mal a modelos locales pequeños (llama3.2), así que Qwen 7B local no debe recibir este rol — igual que el clasificador, un modelo local pequeño va con el prompt genérico, no con una persona larga.

Condensados a ~1.000 caracteres cada uno (los originales tienen 1.300-2.500 palabras) porque en este PC la inferencia local va solo por CPU y el prompt de sistema se paga en cada llamada.

Origen y licencia del material adaptado: https://github.com/msitarzewski/agency-agents (commit 053ddbb, 21/09/2026).

    MIT License
    Copyright (c) 2025 AgentLand Contributors

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
