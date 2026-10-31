# -*- coding: utf-8 -*-
"""Generador determinista de sudokus con solución única, niveles por nº de pistas y sin dependencias."""

from __future__ import annotations

import argparse
import random
from nucleo import ayuda

NIVELES = {"facil": 40, "medio": 32, "dificil": 28}


def valida(rejilla: str | None) -> bool:
    """Valida si una rejilla de 81 caracteres es correcta según las reglas del sudoku."""
    if not isinstance(rejilla, str) or len(rejilla) != 81:
        return False
    if not all(c in "0123456789" for c in rejilla):
        return False

    # Validar filas, columnas y cajas
    for i in range(9):
        # Fila i
        fila = [rejilla[i * 9 + j] for j in range(9) if rejilla[i * 9 + j] != "0"]
        if len(fila) != len(set(fila)):
            return False
        # Columna i
        col = [rejilla[j * 9 + i] for j in range(9) if rejilla[j * 9 + i] != "0"]
        if len(col) != len(set(col)):
            return False

    # Cajas 3x3
    for r in range(0, 9, 3):
        for c in range(0, 9, 3):
            caja = []
            for dr in range(3):
                for dc in range(3):
                    val = rejilla[(r + dr) * 9 + (c + dc)]
                    if val != "0":
                        caja.append(val)
            if len(caja) != len(set(caja)):
                return False

    return True


def _encontrar_vacia(rejilla: str) -> int:
    return rejilla.find("0")


def _obtener_candidatos(rejilla: str, idx: int) -> set[str]:
    fila = idx // 9
    col = idx % 9
    caja_r = (fila // 3) * 3
    caja_c = (col // 3) * 3
    usados = set()

    for i in range(9):
        usados.add(rejilla[fila * 9 + i])
        usados.add(rejilla[i * 9 + col])

    for dr in range(3):
        for dc in range(3):
            usados.add(rejilla[(caja_r + dr) * 9 + (caja_c + dc)])

    return {str(d) for d in range(1, 10)} - usados


_TODOS = 0b1111111110        # bits 1..9


def contar_soluciones(rejilla: str, limite: int = 2) -> int:
    """Cuenta cuántas soluciones tiene la rejilla, deteniéndose al alcanzar el límite.

    Bloque 21 (25/10): con bits por fila/columna/caja y empezando por la casilla con menos candidatos. El número que
    devuelve (min(soluciones, limite)) no depende del orden de búsqueda; antes, con la primera casilla vacía, un
    sudoku "difícil" pedía ~3 millones de pasos y su test tardaba 40-70 s."""
    if not valida(rejilla):
        return 0
    celdas = [int(c) for c in rejilla]
    filas, cols, cajas = [0] * 9, [0] * 9, [0] * 9
    vacias = []
    for i, v in enumerate(celdas):
        if v:
            b = 1 << v
            filas[i // 9] |= b
            cols[i % 9] |= b
            cajas[(i // 27) * 3 + (i % 9) // 3] |= b
        else:
            vacias.append(i)
    contador = 0

    def _resolver_recursivo() -> None:
        nonlocal contador
        mejor, libres, cuantos = -1, 0, 10
        for i in vacias:
            if celdas[i]:
                continue
            m = _TODOS & ~(filas[i // 9] | cols[i % 9] | cajas[(i // 27) * 3 + (i % 9) // 3])
            n = bin(m).count("1")
            if n < cuantos:
                mejor, libres, cuantos = i, m, n
                if n <= 1:
                    break
        if mejor == -1:
            contador += 1
            return
        f, c, k = mejor // 9, mejor % 9, (mejor // 27) * 3 + (mejor % 9) // 3
        while libres:
            b = libres & -libres
            libres ^= b
            celdas[mejor] = b.bit_length() - 1
            filas[f] |= b
            cols[c] |= b
            cajas[k] |= b
            _resolver_recursivo()
            filas[f] ^= b
            cols[c] ^= b
            cajas[k] ^= b
            celdas[mejor] = 0
            if contador >= limite:
                return

    _resolver_recursivo()
    return min(contador, limite)


def resolver(rejilla: str) -> str | None:
    """Resuelve la rejilla y devuelve una solución completa o None si no tiene."""
    if not valida(rejilla):
        return None

    def _resolver_recursivo(r_str: str) -> str | None:
        idx = _encontrar_vacia(r_str)
        if idx == -1:
            return r_str

        candidatos = _obtener_candidatos(r_str, idx)
        for c in sorted(candidatos):
            r_nueva = r_str[:idx] + c + r_str[idx + 1 :]
            res = _resolver_recursivo(r_nueva)
            if res is not None:
                return res
        return None

    return _resolver_recursivo(rejilla)


def generar(semilla: int, pistas: int) -> dict:
    """Genera un sudoku determinista con una solución única y un número objetivo de pistas."""
    rnd = random.Random(semilla)

    # Generar solución completa base
    base = "0" * 81
    # Para asegurar variedad aleatoria con la semilla, rellenamos con backtracking aleatorizado
    def _llenar_aleatorio(r_str: str) -> str | None:
        idx = _encontrar_vacia(r_str)
        if idx == -1:
            return r_str
        cands = list(_obtener_candidatos(r_str, idx))
        rnd.shuffle(cands)
        for c in cands:
            res = _llenar_aleatorio(r_str[:idx] + c + r_str[idx + 1 :])
            if res is not None:
                return res
        return None

    solucion = _llenar_aleatorio(base)
    if not solucion:
        solucion = (
            "534678912672195348198342567859761423426853791713924856961537284287419635345286179"
        )

    puzzle = list(solucion)
    indices = list(range(81))
    rnd.shuffle(indices)

    # Quitar pistas manteniendo solución única
    for idx in indices:
        if puzzle[idx] == "0":
            continue
        pistas_actuales = sum(1 for c in puzzle if c != "0")
        if pistas_actuales <= pistas:
            break

        temp = puzzle[idx]
        puzzle[idx] = "0"
        p_str = "".join(puzzle)

        if contar_soluciones(p_str, limite=2) != 1:
            puzzle[idx] = temp

    p_str = "".join(puzzle)
    num_pistas = sum(1 for c in p_str if c != "0")

    return {"puzzle": p_str, "solucion": solucion, "pistas": num_pistas}


def generar_nivel(semilla: int, nivel: str) -> dict:
    """Genera un sudoku adaptado al nivel de dificultad especificado."""
    if nivel not in NIVELES:
        raise ValueError(f"Nivel desconocido: {nivel}")
    res = generar(semilla, NIVELES[nivel])
    res["nivel"] = nivel
    return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de sudokus con solución única.")
    parser.parse_args()
    ayuda.atender(__doc__)