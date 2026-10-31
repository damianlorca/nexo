# -*- coding: utf-8 -*-
"""Medidas y costes de Amazon KDP para tapa blanda."""

from __future__ import annotations

# Bloque 23 (29/10): la cubierta (T945) mide con kdp.SANGRADO; T939 lo dejaba como 0.125 suelto en cubierta().
SANGRADO = 0.125                 # pulgadas de sangrado de KDP alrededor de la cubierta


def margen_interior(paginas: int) -> float:
    """Devuelve el margen interior en pulgadas según el número de páginas."""
    if not (24 <= paginas <= 828):
        raise ValueError("El número de páginas debe estar entre 24 y 828.")
    if paginas <= 150:
        return 0.375
    elif paginas <= 300:
        return 0.5
    elif paginas <= 500:
        return 0.625
    elif paginas <= 700:
        return 0.75
    else:
        return 0.875


def es_grande(ancho: float, alto: float) -> bool:
    """Determina si un formato es grande (ancho > 6.12 o alto > 9)."""
    return ancho > 6.12 or alto > 9.0


def coste_impresion(paginas: int, mercado: str = "es", ancho: float = 8.5, alto: float = 11.0) -> float:
    """Calcula el coste de impresión en función de las páginas, mercado y dimensiones."""
    if not (24 <= paginas <= 828):
        raise ValueError("Páginas fuera de rango (24-828).")
    if mercado not in ("es", "com"):
        raise ValueError(f"Mercado desconocido: {mercado}")

    grande = es_grande(ancho, alto)

    if mercado == "es":
        if paginas <= 110:
            return 2.48 if grande else 2.05
        else:
            fijo = 0.75
            por_pagina = 0.016 if grande else 0.012
            return round(fijo + por_pagina * paginas, 2)
    elif mercado == "com":
        if paginas <= 110:
            return 2.84 if grande else 2.30
        else:
            fijo = 1.00
            por_pagina = 0.017 if grande else 0.012
            return round(fijo + por_pagina * paginas, 2)


def regalia(precio: float, paginas: int, mercado: str = "es", ancho: float = 8.5, alto: float = 11.0) -> dict:
    """Calcula la regalía y retorna un diccionario con tasa, impresión y regalía."""
    tasa = 0.6 if precio >= 9.99 else 0.5
    impresion = coste_impresion(paginas, mercado, ancho, alto)
    valor_regalia = round(tasa * precio - impresion, 2)
    return {
        "tasa": tasa,
        "impresion": impresion,
        "regalia": valor_regalia,
    }


def cubierta(paginas: int, papel: str = "blanco", ancho: float = 8.5, alto: float = 11.0) -> dict:
    """Calcula las medidas de la cubierta completa de tapa blanda."""
    if papel not in ("blanco", "crema"):
        raise ValueError(f"Papel desconocido: {papel}")

    grosor = 0.002252 if papel == "blanco" else 0.0025
    lomo = round(paginas * grosor, 4)
    ancho_total = round(2 * ancho + lomo + 2 * SANGRADO, 4)
    alto_total = round(alto + 2 * SANGRADO, 4)
    texto_lomo = paginas > 79

    return {
        "lomo": lomo,
        "ancho_total": ancho_total,
        "alto_total": alto_total,
        "texto_lomo": texto_lomo,
    }


if __name__ == "__main__":
    from nucleo import ayuda
    ayuda.atender(__doc__)