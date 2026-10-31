# -*- coding: utf-8 -*-
"""Plan de páginas del libro de sudokus (T689, pieza P1a).

Define qué va en cada página del libro: portadilla, instrucciones, puzzles,
soluciones y, si el total queda impar, una página en blanco al final para
garantizar que el número total de páginas sea par (requisito de KDP para
impresión a doble cara).

Contrato:
    plan_paginas(n_puzzles, por_pagina=2, soluciones_por_pagina=6) -> list[dict]
    paginas_totales(n_puzzles, por_pagina=2, soluciones_por_pagina=6) -> int

Cada página es un dict con claves:
    "numero": int (1..N consecutivo)
    "tipo": str ("portadilla", "instrucciones", "puzzle", "soluciones", "blanca")
    "indices": list[int] (índices 0-based de puzzles; [] para portadilla,
              instrucciones y blanca)

Validaciones:
    - n_puzzles >= 1
    - por_pagina en (1, 2, 4)
    - soluciones_por_pagina en (4, 6, 9)
"""
from __future__ import annotations

import math


def plan_paginas(n_puzzles: int, por_pagina: int = 2, soluciones_por_pagina: int = 6) -> list[dict]:
    """Devuelve la lista de páginas del libro de sudokus.

    Args:
        n_puzzles: Número total de puzzles (>= 1).
        por_pagina: Puzzles por página (1, 2 o 4).
        soluciones_por_pagina: Soluciones por página (4, 6 o 9).

    Returns:
        Lista de dicts, cada uno con "numero", "tipo" e "indices".

    Raises:
        ValueError: Si n_puzzles < 1, por_pagina no está en (1, 2, 4) o
                    soluciones_por_pagina no está en (4, 6, 9).
    """
    if n_puzzles < 1:
        raise ValueError("n_puzzles debe ser >= 1")
    if por_pagina not in (1, 2, 4):
        raise ValueError("por_pagina debe ser 1, 2 o 4")
    if soluciones_por_pagina not in (4, 6, 9):
        raise ValueError("soluciones_por_pagina debe ser 4, 6 o 9")

    paginas: list[dict] = []

    # Portadilla
    paginas.append({"tipo": "portadilla", "indices": []})

    # Instrucciones
    paginas.append({"tipo": "instrucciones", "indices": []})

    # Páginas de puzzles
    num_pag_puzzles = math.ceil(n_puzzles / por_pagina)
    for i in range(num_pag_puzzles):
        inicio = i * por_pagina
        fin = min(inicio + por_pagina, n_puzzles)
        paginas.append({"tipo": "puzzle", "indices": list(range(inicio, fin))})

    # Páginas de soluciones
    num_pag_soluciones = math.ceil(n_puzzles / soluciones_por_pagina)
    for i in range(num_pag_soluciones):
        inicio = i * soluciones_por_pagina
        fin = min(inicio + soluciones_por_pagina, n_puzzles)
        paginas.append({"tipo": "soluciones", "indices": list(range(inicio, fin))})

    # Página en blanco si el total es impar
    if len(paginas) % 2 != 0:
        paginas.append({"tipo": "blanca", "indices": []})

    # Asignar números consecutivos
    for idx, pagina in enumerate(paginas, start=1):
        pagina["numero"] = idx

    return paginas


def paginas_totales(n_puzzles: int, por_pagina: int = 2, soluciones_por_pagina: int = 6) -> int:
    """Devuelve el número total de páginas del libro.

    Args:
        n_puzzles: Número total de puzzles (>= 1).
        por_pagina: Puzzles por página (1, 2 o 4).
        soluciones_por_pagina: Soluciones por página (4, 6 o 9).

    Returns:
        Número total de páginas (siempre par).

    Raises:
        ValueError: Si n_puzzles < 1, por_pagina no está en (1, 2, 4) o
                    soluciones_por_pagina no está en (4, 6, 9).
    """
    return len(plan_paginas(n_puzzles, por_pagina, soluciones_por_pagina))


if __name__ == "__main__":
    from nucleo import ayuda; ayuda.atender(__doc__)