# Herramientas archivadas

Scripts de un solo uso que ya cumplieron su función: consultas multi-IA de las fases 2 y 3,
demos del 12/09, exploración de selectores web (T147), el parche T112 ya aplicado y el banco
de roles de T100 (lo sustituyó `banco_roles_v2.py`). Se archivaron en la auditoría N01
(hallazgo H19, 25/09/2026).

- Ningún código de NEXO los importa ni los lanza: se comprobó con grep antes de moverlos.
- Se guardan aquí, versionados, y no en `_archivo/`, porque `_archivo/` está en `.gitignore`
  y se perderían del repositorio. Regla de CLAUDE.md: no borrar, archivar.
- **No ejecutar desde aquí.** Calculan rutas relativas a su sitio original. `_cerrar2.py`,
  además, reescribiría `memoria/estado.json` con datos del 12/09.
