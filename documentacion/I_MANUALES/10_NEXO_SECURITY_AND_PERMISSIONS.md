# I.10 NEXO_SECURITY_AND_PERMISSIONS

Ver evidencia completa y línea a línea en `B_AUDITORIA_REAL.md` secciones B.2 y B.4. Este manual resume el modelo, no repite el código.

## Modelo de tres niveles (`nucleo/permisos.py`, verificado)

- **VERDE**: sin preguntar. Dentro de la zona verde (`config.toml [permisos] zona_verde`, hoy la raíz del proyecto).
- **ÁMBAR**: pide aprobación (`NecesitaAprobacion`), se repite la llamada con `aprobado=True` tras que Damián diga que sí. Cubre: gestores de paquetes, `git push`, descargas, persistencia de arranque, configuración de sistema, y cualquier escritura a un archivo blindado o fuera de zona verde.
- **ROJO**: bloqueado sin excepción (`Bloqueado`). Formatear disco, `diskpart`, `cipher /w`, `bcdedit`, `shutdown`, `vssadmin delete`, borrado (`del`, `rm -rf`, `Remove-Item`, etc.), y cualquier operación sobre `secretos.toml`.

## Archivos blindados (`ARCHIVOS_BLINDADOS`)

`nucleo/permisos.py`, `nucleo/instancia.py`, `nucleo/config.py`, `manos/shell.py`, `manos/archivos.py`, `manos/servidor_mcp.py`. Escribir sobre ellos da ÁMBAR (pide aprobación), no ROJO — la protección real contra un cambio invisible es Git, no una barrera técnica que lo impida del todo. Nunca modificar estos sin aprobación explícita de Damián en el momento, sea cual sea la excusa.

## Agujeros conocidos, abiertos, con decisión pendiente de Damián (no tocar sin su aprobación)

- **T016/L1**: `ejecutar_python` no pasa por este sistema en absoluto, y acepta rutas absolutas fuera del proyecto sin restricción.
- **B5**: `manos/shell.py::vivo()` llama a `ejecutar(..., aprobado=True)` con el argumento escrito a mano en el código, saltándose el gate para ese caso.
- **REQ-070** (hallazgo nuevo de esta auditoría): lectura de cualquier ruta absoluta fuera del proyecto es VERDE (sin preguntar), salvo `secretos.toml`.
- **T024/L6**: el filtro mira la línea entera de PowerShell (comillas y argumentos incluidos), no solo la orden. Arreglarlo bien pide un analizador de línea, no otra regex. Decisión propia de Damián de no tocarlo sin pruebas y con calma.

## Regla de credenciales

`secretos.toml` nunca se lee con `leer()` normal (da ROJO). El acceso indirecto es siempre vía `nucleo.config.valor(...)`. Nunca imprimir un token en un log o en la salida de una herramienta — lección aprendida por error real esta misma auditoría (ver `B_AUDITORIA_REAL.md` y el historial del turno de Telegram del 12/09): nunca encadenar redacción de un secreto después de impresión en una sola línea de PowerShell sin comprobarlo antes.
