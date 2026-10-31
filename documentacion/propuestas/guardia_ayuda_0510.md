# Propuesta: --help en nucleo/guardia_python.py, bien hecho (05/10/2026)

Estado: **HECHO Y TESTEADO en un worktree aparte; NO aplicado en principal** (lo aplica Damián o el coordinador tras ver el diff).

## Qué pasó
El parche `ayuda_entradas_0510.patch` añadía a la guardia `from nucleo import ayuda; ayuda.atender(__doc__)`.
La guardia se lanza como script (`python nucleo/guardia_python.py script.py ...`), así que `sys.path[0]` es `nucleo/`
y `import nucleo` falla: ModuleNotFoundError en **todos** los `ejecutar_python`. La comprobación estática del test de
ayudas no lo vio; `tests/test_t708_guardia_tope.py` sí (único rojo de la suite del 05/10: 1 fallo, 1755 en verde).
Por eso la guardia quedó fuera del commit `908b541`.

## El arreglo (`guardia_ayuda_0510.patch`, contra `principal` con la línea rota ya revertida)
```python
if __name__ == "__main__":
    if str(RAIZ) not in sys.path: sys.path.append(str(RAIZ))
    from nucleo import ayuda; ayuda.atender(__doc__, sys.argv[1:2])
    raise SystemExit(main(sys.argv[1:]))
```
- La raíz se **añade al final** (`append`), igual que ya hace `instalar()`. No se inserta delante, porque `main()` cambia
  `sys.path[0]` por la carpeta del script: con `insert(0)` se colaría `nucleo/` en el `sys.path` del script vigilado
  (`import config` cogería `nucleo/config.py`).
- **Solo mira el primer argumento** (`sys.argv[1:2]`). Con `ayuda.atender(__doc__)` a secas,
  `guardia_python.py script.py --help` imprimía la ayuda de la guardia en vez de pasar el `--help` al script.
- Quita la guardia de los excluidos de `tests/test_ayuda_entradas.py` y añade `tests/test_guardia_ayuda.py`, que
  **ejecuta** la guardia en un subproceso: `--help` (sale con 0 y su ayuda), un script normal (corre, recibe sus
  argumentos, `sys.path[0]` es su carpeta y `nucleo/` no está en `sys.path`), `script.py --help` (la ayuda es la del
  script) y sin argumentos (uso, código 2).

## Evidencia
- Con el parche aplicado sobre HEAD: `test_guardia_ayuda` + `test_t708_guardia_tope` + `test_ayuda_entradas` = 58 en
  verde (5 omitidos: los subprocesos de `test_ayuda_entradas` necesitan `.venv` en la raíz del worktree; en principal
  sí corren).
- Con la línea rota del 05/10: los 4 tests nuevos y el de T708 fallan (5 en rojo). O sea, el test sí detecta este fallo.

## Aplicar (después de que el coordinador revierta la línea rota)
```
git apply documentacion/propuestas/guardia_ayuda_0510.patch
.venv\Scripts\python.exe -m pytest tests\test_guardia_ayuda.py tests\test_t708_guardia_tope.py tests\test_ayuda_entradas.py -q
```
