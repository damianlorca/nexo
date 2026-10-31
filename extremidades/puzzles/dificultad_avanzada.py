# -*- coding: utf-8 -*-
"""Resolvedor lógico avanzado de sudokus y graduación en 4 niveles (libro «Sudoku 1 · Cuadernos de Lógica»).

Por qué: con las técnicas básicas de `dificultad.py` los sudokus «expertos» se quedan atascados y no se sabe si un
humano puede resolverlos sin adivinar. Aquí se añaden las técnicas de los resolvedores humanos, de la más fácil a la
más difícil:

  solitario_desnudo, solitario_oculto, bloqueo, pareja_desnuda, pareja_oculta       (las de `dificultad.py`)
  tripleta_desnuda, tripleta_oculta, x_wing, swordfish, xy_wing, xyz_wing, w_wing,
  coloreado (cadenas simples: «simple coloring»), xy_chain, aic (cadenas alternas de inferencias)

Nada de ensayo y error ni backtracking dentro del resolvedor: cada paso es una deducción válida sobre los candidatos
actuales. En cada paso se aplica UNA vez la primera técnica (en ese orden) que cambie algo y se vuelve a empezar por
la primera. `nivel4` etiqueta: facil (solo solitario desnudo), medio (hasta solitario oculto), dificil (hasta bloqueos
y parejas), experto (necesita alguna técnica avanzada y se resuelve entera con ellas) o no_logico (no se resuelve).

Generador: `generar_por_nivel4(semilla, nivel)` -> sudoku de solución única (comprobada con un contador propio de
máscaras de bits, mucho más rápido que `sudoku.contar_soluciones`) con `nivel4 == nivel`, determinista por semilla.
"""
from __future__ import annotations

import random
from itertools import combinations

from extremidades.puzzles import sudoku

TECNICAS = (
    "solitario_desnudo", "solitario_oculto", "bloqueo", "pareja_desnuda", "pareja_oculta",
    "tripleta_desnuda", "tripleta_oculta", "x_wing", "swordfish", "xy_wing", "xyz_wing", "w_wing",
    "coloreado", "xy_chain", "aic",
)
BASICAS = TECNICAS[:5]
NIVELES4 = ("facil", "medio", "dificil", "experto", "no_logico")

# Peso de cada técnica en la puntuación (suma sobre todos los pasos). Las cadenas suman algo más por eslabón.
PESOS = {
    "solitario_desnudo": 1, "solitario_oculto": 2, "bloqueo": 5, "pareja_desnuda": 8, "pareja_oculta": 10,
    "tripleta_desnuda": 14, "tripleta_oculta": 18, "x_wing": 22, "swordfish": 30, "xy_wing": 34, "xyz_wing": 38,
    "w_wing": 42, "coloreado": 46, "xy_chain": 55, "aic": 65,
}
_POR_ESLABON = {"xy_chain": 3, "aic": 4}
_LARGO_MAX_AIC = 7          # eslabones fuertes máximos de una cadena AIC

_PISTAS_NIVEL = {"facil": 40, "medio": 32, "dificil": 26, "experto": 0}   # 0: se quita hasta que no se pueda más
_PISTAS_MAX_EXPERTO = 28
UMBRAL_EXPERTO = 200        # puntuación mínima de un experto generado (los «extremo» reales de UsDoku dan 176 y 293)
PUNTUACION_MAX_EXPERTO = 900  # por encima, las cadenas son demasiado largas para un cuaderno de pasatiempos

_BIT = [0] + [1 << d for d in range(1, 10)]
_TODAS = 0x3FE
_POP = [bin(m).count("1") for m in range(1024)]
_DIGS = [tuple(d for d in range(1, 10) if m & (1 << d)) for m in range(1024)]

_FILAS = [tuple(f * 9 + c for c in range(9)) for f in range(9)]
_COLS = [tuple(f * 9 + c for f in range(9)) for c in range(9)]
_CAJAS = [tuple((bf * 3 + i) * 9 + bc * 3 + j for i in range(3) for j in range(3)) for bf in range(3) for bc in range(3)]
_UNIDADES = _FILAS + _COLS + _CAJAS
_UNIDADES_DE = [tuple(u for u in _UNIDADES if i in u) for i in range(81)]
_UNIDAD_IDX_DE = [tuple(n for n, u in enumerate(_UNIDADES) if i in u) for i in range(81)]
_VECINOS = [tuple(sorted(set().union(*_UNIDADES_DE[i]) - {i})) for i in range(81)]
_VEN = [frozenset(v) for v in _VECINOS]
_BLOQUEOS = []
for _caja in _CAJAS:
    for _linea in _FILAS + _COLS:
        _comun = tuple(i for i in _caja if i in _linea)
        if _comun:
            _BLOQUEOS.append((_comun, tuple(i for i in _caja if i not in _comun),
                              tuple(i for i in _linea if i not in _comun)))


# ------------------------------------------------------------------------------------------------ estado
def _candidatos(celdas):
    cand = [0] * 81
    for i in range(81):
        if not celdas[i]:
            usados = 0
            for j in _VECINOS[i]:
                usados |= _BIT[celdas[j]] if celdas[j] else 0
            cand[i] = _TODAS & ~usados
    return cand


def _poner(celdas, cand, i, d):
    celdas[i] = d
    cand[i] = 0
    b = ~_BIT[d]
    for j in _VECINOS[i]:
        cand[j] &= b


def _quitar(cand, celdas_iter, d):
    """Quita el dígito d de esas casillas; True si cambió algo."""
    b = _BIT[d]
    cambio = False
    for k in celdas_iter:
        if cand[k] & b:
            cand[k] &= ~b
            cambio = True
    return cambio


# ------------------------------------------------------------------------------------------------ básicas
def _solitario_desnudo(celdas, cand):
    for i in range(81):
        m = cand[i]
        if m and not m & (m - 1):
            _poner(celdas, cand, i, m.bit_length() - 1)
            return True
    return False


def _solitario_oculto(celdas, cand):
    for u in _UNIDADES:
        for d in range(1, 10):
            b = _BIT[d]
            sitios = [i for i in u if cand[i] & b]
            if len(sitios) == 1:
                _poner(celdas, cand, sitios[0], d)
                return True
    return False


def _bloqueo(celdas, cand):
    for comun, resto_caja, resto_linea in _BLOQUEOS:
        for d in range(1, 10):
            b = _BIT[d]
            en_comun = any(cand[i] & b for i in comun)
            if not en_comun:
                continue
            en_caja = any(cand[i] & b for i in resto_caja)
            en_linea = any(cand[i] & b for i in resto_linea)
            if not en_caja and en_linea:                    # en la caja solo cabe en la línea
                return _quitar(cand, resto_linea, d)
            if not en_linea and en_caja:                    # en la línea solo cabe en la caja
                return _quitar(cand, resto_caja, d)
    return False


def _desnudas(k):
    def paso(celdas, cand):
        for u in _UNIDADES:
            celdas_k = [i for i in u if 2 <= _POP[cand[i]] <= k]
            for combo in combinations(celdas_k, k):
                union = 0
                for i in combo:
                    union |= cand[i]
                if _POP[union] != k:
                    continue
                cambio = False
                for i in u:
                    if i not in combo and cand[i] & union:
                        cand[i] &= ~union
                        cambio = True
                if cambio:
                    return True
        return False
    return paso


def _ocultas(k):
    def paso(celdas, cand):
        for u in _UNIDADES:
            sitios = {}
            for d in range(1, 10):
                s = tuple(i for i in u if cand[i] & _BIT[d])
                if 2 <= len(s) <= k:
                    sitios[d] = s
            for combo in combinations(sitios, k):
                celdas_u = set()
                for d in combo:
                    celdas_u.update(sitios[d])
                if len(celdas_u) != k:
                    continue
                mascara = sum(_BIT[d] for d in combo)
                cambio = False
                for i in celdas_u:
                    if cand[i] & ~mascara:
                        cand[i] &= mascara
                        cambio = True
                if cambio:
                    return True
        return False
    return paso


# ------------------------------------------------------------------------------------------------ peces
def _pez(n):
    def paso(celdas, cand):
        for d in range(1, 10):
            b = _BIT[d]
            for por_filas in (True, False):
                lineas = []
                for li in range(9):
                    linea = _FILAS[li] if por_filas else _COLS[li]
                    pos = tuple((k % 9) if por_filas else (k // 9) for k in linea if cand[k] & b)
                    if 2 <= len(pos) <= n:
                        lineas.append((li, pos))
                for combo in combinations(lineas, n):
                    cubre = set()
                    for _, pos in combo:
                        cubre.update(pos)
                    if len(cubre) != n:
                        continue
                    base = {li for li, _ in combo}
                    cambio = False
                    for ci in cubre:
                        for k in (_COLS[ci] if por_filas else _FILAS[ci]):
                            if (k // 9 if por_filas else k % 9) not in base and cand[k] & b:
                                cand[k] &= ~b
                                cambio = True
                    if cambio:
                        return True
        return False
    return paso


# ------------------------------------------------------------------------------------------------ alas
def _bivalor(cand):
    return [i for i in range(81) if _POP[cand[i]] == 2]


def _xy_wing(celdas, cand):
    biv = _bivalor(cand)
    for p in biv:
        mp = cand[p]
        alas = [w for w in _VECINOS[p] if _POP[cand[w]] == 2]
        for w1 in alas:
            comun = cand[w1] & mp
            if _POP[comun] != 1:
                continue
            z = cand[w1] & ~mp
            m2 = (mp & ~comun) | z
            for w2 in alas:
                if w2 != w1 and cand[w2] == m2:
                    if _quitar(cand, [k for k in _VEN[w1] & _VEN[w2] if k != p], z.bit_length() - 1):
                        return True
    return False


def _xyz_wing(celdas, cand):
    for p in range(81):
        mp = cand[p]
        if _POP[mp] != 3:
            continue
        for z in _DIGS[mp]:
            bz = _BIT[z]
            x, y = _DIGS[mp & ~bz]
            m1, m2 = _BIT[x] | bz, _BIT[y] | bz
            for w1 in (w for w in _VECINOS[p] if cand[w] == m1):
                for w2 in (w for w in _VECINOS[p] if cand[w] == m2):
                    if _quitar(cand, _VEN[p] & _VEN[w1] & _VEN[w2], z):
                        return True
    return False


def _enlaces_fuertes(cand, d):
    """Pares de casillas que son las dos únicas de una unidad con el candidato d."""
    b = _BIT[d]
    out = []
    for u in _UNIDADES:
        s = [i for i in u if cand[i] & b]
        if len(s) == 2:
            out.append((s[0], s[1]))
    return out


def _w_wing(celdas, cand):
    fuertes = {}
    for a, c in combinations(_bivalor(cand), 2):
        if cand[a] != cand[c] or c in _VEN[a]:
            continue
        comunes = _VEN[a] & _VEN[c]
        d1, d2 = _DIGS[cand[a]]
        for x, y in ((d1, d2), (d2, d1)):
            if not any(cand[k] & _BIT[x] for k in comunes):
                continue
            if y not in fuertes:
                fuertes[y] = _enlaces_fuertes(cand, y)
            for p, q in fuertes[y]:
                if (p in _VEN[a] and q in _VEN[c]) or (p in _VEN[c] and q in _VEN[a]):
                    if _quitar(cand, comunes, x):
                        return True
    return False


# ------------------------------------------------------------------------------------------------ cadenas
def _coloreado(celdas, cand):
    for d in range(1, 10):
        b = _BIT[d]
        enlaces = _enlaces_fuertes(cand, d)
        if len(enlaces) < 2:
            continue
        ady = {}
        for p, q in enlaces:
            ady.setdefault(p, []).append(q)
            ady.setdefault(q, []).append(p)
        visto = set()
        for inicio in sorted(ady):
            if inicio in visto:
                continue
            color = {inicio: 0}
            pila = [inicio]
            while pila:
                x = pila.pop()
                for y in ady[x]:
                    if y not in color:
                        color[y] = 1 - color[x]
                        pila.append(y)
            visto.update(color)
            if len(color) < 4:
                continue
            for c in (0, 1):                                   # envoltura de color: dos del mismo color se ven
                mismos = [k for k in sorted(color) if color[k] == c]
                if any(v in _VEN[k] for k, v in combinations(mismos, 2)):
                    if _quitar(cand, mismos, d):
                        return True
            objetivo = [k for k in range(81) if cand[k] & b and k not in color]
            quitar = [k for k in objetivo
                      if any(color[j] == 0 for j in _VEN[k] if j in color) and any(color[j] == 1 for j in _VEN[k] if j in color)]
            if quitar and _quitar(cand, quitar, d):            # trampa de color
                return True
    return False


def _xy_chain(celdas, cand):
    biv = _bivalor(cand)
    vecinos_biv = {i: [j for j in _VECINOS[i] if _POP[cand[j]] == 2] for i in biv}
    mejor = None
    for a in biv:
        for x in _DIGS[cand[a]]:
            salida0 = cand[a] & ~_BIT[x]
            pila = [(a, salida0, (a,))]
            while pila:
                ultimo, salida, camino = pila.pop()
                for j in vecinos_biv[ultimo]:
                    if j in camino or not cand[j] & salida:
                        continue
                    nueva = cand[j] & ~salida
                    if nueva == _BIT[x] and len(camino) >= 2:
                        elim = [k for k in _VEN[a] & _VEN[j] if cand[k] & _BIT[x]]
                        if elim and (mejor is None or len(camino) + 1 < mejor[0]):
                            mejor = (len(camino) + 1, elim, x)
                    elif len(camino) + 1 < 10:
                        pila.append((j, nueva, camino + (j,)))
    if mejor:
        largo, elim, x = mejor
        _quitar(cand, elim, x)
        return PESOS["xy_chain"] + _POR_ESLABON["xy_chain"] * (largo - 3)
    return False


def _aic(celdas, cand):
    """Cadena alterna de inferencias: S falso => E verdadero (empieza y acaba en enlace fuerte).
    Todo candidato débilmente enlazado a S y a E (misma casilla, o mismo dígito y se ven) se elimina."""
    nodos = [i * 9 + d - 1 for i in range(81) for d in _DIGS[cand[i]]]
    sitios = {}
    for ui, u in enumerate(_UNIDADES):
        for d in range(1, 10):
            sitios[(ui, d)] = [i for i in u if cand[i] & _BIT[d]]
    fuertes = {n: [] for n in nodos}
    for n in nodos:
        i, d = divmod(n, 9)
        d += 1
        if _POP[cand[i]] == 2:
            fuertes[n].append(i * 9 + (cand[i] & ~_BIT[d]).bit_length() - 2)
        for ui in _UNIDAD_IDX_DE[i]:
            s = sitios[(ui, d)]
            if len(s) == 2:
                m = (s[0] if s[1] == i else s[1]) * 9 + d - 1
                if m not in fuertes[n]:
                    fuertes[n].append(m)
    memo = {}

    def debiles(n):
        r = memo.get(n)
        if r is None:
            i, d = divmod(n, 9)
            d += 1
            b = _BIT[d]
            r = {i * 9 + e - 1 for e in _DIGS[cand[i]] if e != d}
            r.update(j * 9 + d - 1 for j in _VECINOS[i] if cand[j] & b)
            memo[n] = r
        return r

    mejor = None                                     # (eslabones fuertes, comunes)
    for s in nodos:
        if not fuertes[s]:
            continue
        ws = debiles(s)
        visto = {s}
        frontera = [t for t in fuertes[s] if t not in visto]
        visto.update(frontera)
        k = 1
        while frontera and k <= _LARGO_MAX_AIC and (mejor is None or k < mejor[0]):
            hallado = None
            for e in frontera:
                comunes = ws & debiles(e)
                if comunes:
                    hallado = comunes
                    break
            if hallado:
                mejor = (k, hallado)
                break
            nueva = []
            for t in frontera:
                for m in debiles(t):
                    for u in fuertes.get(m, ()):
                        if u not in visto:
                            visto.add(u)
                            nueva.append(u)
            frontera = nueva
            k += 1
    if mejor is None:
        return False
    k, comunes = mejor
    cambio = False
    for n in comunes:
        i, d = divmod(n, 9)
        if cand[i] & _BIT[d + 1]:
            cand[i] &= ~_BIT[d + 1]
            cambio = True
    return (PESOS["aic"] + _POR_ESLABON["aic"] * (k - 1)) if cambio else False


_PASOS = {
    "solitario_desnudo": _solitario_desnudo, "solitario_oculto": _solitario_oculto, "bloqueo": _bloqueo,
    "pareja_desnuda": _desnudas(2), "pareja_oculta": _ocultas(2), "tripleta_desnuda": _desnudas(3),
    "tripleta_oculta": _ocultas(3), "x_wing": _pez(2), "swordfish": _pez(3), "xy_wing": _xy_wing,
    "xyz_wing": _xyz_wing, "w_wing": _w_wing, "coloreado": _coloreado, "xy_chain": _xy_chain, "aic": _aic,
}


# ------------------------------------------------------------------------------------------------ API
def resolver_avanzado(rejilla: str) -> dict:
    """Resuelve solo con lógica. -> {resuelto, rejilla, tecnicas: {nombre: veces}, maxima, puntuacion}."""
    if not sudoku.valida(rejilla):
        raise ValueError("rejilla no válida")
    celdas = [int(c) for c in rejilla]
    cand = _candidatos(celdas)
    usadas = {t: 0 for t in TECNICAS}
    puntos = 0
    atascado = False
    while not atascado:
        atascado = True
        for t in TECNICAS:
            r = _PASOS[t](celdas, cand)
            if r:
                usadas[t] += 1
                puntos += r if r is not True else PESOS[t]
                atascado = False
                break
    hechas = [t for t in TECNICAS if usadas[t]]
    return {"resuelto": all(celdas), "rejilla": "".join(map(str, celdas)), "tecnicas": usadas,
            "maxima": hechas[-1] if hechas else None, "puntuacion": puntos}


def nivel4(rejilla: str) -> str:
    """facil | medio | dificil | experto | no_logico."""
    r = resolver_avanzado(rejilla)
    if not r["resuelto"]:
        return "no_logico"
    if r["maxima"] in (None, "solitario_desnudo"):
        return "facil"
    if r["maxima"] == "solitario_oculto":
        return "medio"
    if r["maxima"] in BASICAS:
        return "dificil"
    return "experto"


# ------------------------------------------------------------------------------------------------ generador
def _contar(celdas: list[int], limite: int = 2) -> int:
    """Número de soluciones (hasta `limite`) con máscaras de bits y casilla de menos opciones primero."""
    filas = [0] * 9
    cols = [0] * 9
    cajas = [0] * 9
    vacias = []
    for i, v in enumerate(celdas):
        f, c = divmod(i, 9)
        if v:
            b = 1 << v
            if filas[f] & b or cols[c] & b or cajas[(f // 3) * 3 + c // 3] & b:
                return 0
            filas[f] |= b
            cols[c] |= b
            cajas[(f // 3) * 3 + c // 3] |= b
        else:
            vacias.append(i)
    total = 0

    def rec(pend):
        nonlocal total
        if total >= limite:
            return
        if not pend:
            total += 1
            return
        mejor, mejor_m, mejor_n = -1, 0, 10
        for k, i in enumerate(pend):
            f, c = divmod(i, 9)
            m = _TODAS & ~(filas[f] | cols[c] | cajas[(f // 3) * 3 + c // 3])
            n = _POP[m]
            if n < mejor_n:
                mejor, mejor_m, mejor_n = k, m, n
                if n <= 1:
                    break
        if mejor_n == 0:
            return
        i = pend[mejor]
        resto = pend[:mejor] + pend[mejor + 1:]
        f, c = divmod(i, 9)
        cj = (f // 3) * 3 + c // 3
        for d in _DIGS[mejor_m]:
            b = 1 << d
            filas[f] |= b
            cols[c] |= b
            cajas[cj] |= b
            rec(resto)
            filas[f] &= ~b
            cols[c] &= ~b
            cajas[cj] &= ~b
            if total >= limite:
                return

    rec(vacias)
    return total


def contar_soluciones(rejilla: str, limite: int = 2) -> int:
    """Igual que sudoku.contar_soluciones pero rápido."""
    if not sudoku.valida(rejilla):
        return 0
    return _contar([int(c) for c in rejilla], limite)


def _solucion_aleatoria(rng: random.Random) -> str:
    filas = [0] * 9
    cols = [0] * 9
    cajas = [0] * 9
    celdas = [0] * 81

    def rec(n):
        if n == 81:
            return True
        mejor, mejor_m, mejor_n = -1, 0, 10
        for i in range(81):
            if celdas[i]:
                continue
            f, c = divmod(i, 9)
            m = _TODAS & ~(filas[f] | cols[c] | cajas[(f // 3) * 3 + c // 3])
            if _POP[m] < mejor_n:
                mejor, mejor_m, mejor_n = i, m, _POP[m]
        if mejor_n == 0:
            return False
        f, c = divmod(mejor, 9)
        cj = (f // 3) * 3 + c // 3
        ds = list(_DIGS[mejor_m])
        rng.shuffle(ds)
        for d in ds:
            b = 1 << d
            celdas[mejor] = d
            filas[f] |= b
            cols[c] |= b
            cajas[cj] |= b
            if rec(n + 1):
                return True
            celdas[mejor] = 0
            filas[f] &= ~b
            cols[c] &= ~b
            cajas[cj] &= ~b
        return False

    rec(0)
    return "".join(map(str, celdas))


def _quitar_pistas(solucion: str, rng: random.Random, objetivo: int) -> list[int]:
    """Quita pistas en orden aleatorio manteniendo solución única hasta llegar a `objetivo` (0 = lo mínimo)."""
    celdas = [int(c) for c in solucion]
    orden = list(range(81))
    rng.shuffle(orden)
    pistas = 81
    for i in orden:
        if pistas <= objetivo:
            break
        v = celdas[i]
        celdas[i] = 0
        if _contar(celdas) == 1:
            pistas -= 1
        else:
            celdas[i] = v
    return celdas


def _ficha(celdas, solucion, nivel, semilla, r):
    return {"puzzle": "".join(map(str, celdas)), "solucion": solucion, "pistas": sum(1 for c in celdas if c),
            "nivel": nivel, "puntuacion": r["puntuacion"], "tecnicas": {t: n for t, n in r["tecnicas"].items() if n},
            "semilla": semilla}


def generar_por_nivel4(semilla: int, nivel: str, intentos: int = 400) -> dict:
    """Sudoku de solución única con nivel4 == nivel; determinista. Prueba la sub-semilla semilla*1000 + k."""
    if nivel not in _PISTAS_NIVEL:
        raise ValueError(f"nivel no generable: {nivel}")
    for k in range(intentos):
        rng = random.Random(semilla * 1000 + k)
        solucion = _solucion_aleatoria(rng)
        celdas = _quitar_pistas(solucion, rng, _PISTAS_NIVEL[nivel])
        if nivel == "experto":
            celdas = _hacia_experto(celdas, solucion, rng)
            if celdas is None:
                continue
        puzzle = "".join(map(str, celdas))
        r = resolver_avanzado(puzzle)
        if nivel4(puzzle) != nivel:
            continue
        if nivel == "experto" and (not UMBRAL_EXPERTO <= r["puntuacion"] <= PUNTUACION_MAX_EXPERTO or sum(1 for c in celdas if c) > _PISTAS_MAX_EXPERTO):
            continue
        return _ficha(celdas, solucion, nivel, semilla, r)
    raise RuntimeError(f"sin puzzle de nivel {nivel} en {intentos} intentos")


def _hacia_experto(celdas, solucion, rng):
    """Si el mínimo no se resuelve con lógica, devuelve pistas (una a una) hasta que sí; si ya es solvable, tal cual."""
    celdas = list(celdas)
    for _ in range(12):
        if resolver_avanzado("".join(map(str, celdas)))["resuelto"]:
            return celdas
        vacias = [i for i, c in enumerate(celdas) if not c]
        i = rng.choice(vacias)
        celdas[i] = int(solucion[i])
    return None
