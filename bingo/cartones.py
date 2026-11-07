"""Cartones de bingo, bombos y comprobación de premios.

Un cartón es una rejilla de 5x5. La columna B lleva números del 1 al 15, la I del
16 al 30, la N del 31 al 45 (el centro es libre), la G del 46 al 60 y la O del 61
al 75. Es el bingo de 75 bolas, el más jugado en Venezuela y en toda América.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

# Rango de cada columna: B, I, N, G, O.
RANGOS: tuple[tuple[int, int], ...] = ((1, 15), (16, 30), (31, 45), (46, 60), (61, 75))
LETRAS = ("B", "I", "N", "G", "O")
LIBRE = (2, 2)  # fila, columna del centro (0-indexado)


class ErrorDeBingo(ValueError):
    """Cartón, bola o patrón mal formados."""


@dataclass
class Carton:
    """Un cartón de 5x5. Los números van por filas."""

    numeros: tuple[tuple[int, ...], ...]
    id: str = ""
    # Patrones que este cartón puede cantar (se comprueba contra las bolas).
    marcados: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        if len(self.numeros) != 5 or any(len(f) != 5 for f in self.numeros):
            raise ErrorDeBingo("El cartón tiene que ser una rejilla de 5x5.")
        for col, (lo, hi) in enumerate(RANGOS):
            for fila in range(5):
                if (fila, col) == LIBRE:
                    continue
                n = self.numeros[fila][col]
                if not lo <= n <= hi:
                    raise ErrorDeBingo(
                        f"El número {n} no cabe en la columna {LETRAS[col]} ({lo}-{hi})."
                    )
        self.marcados = {LIBRE}

    def marcar(self, numero: int) -> bool:
        """Marca un número si está en el cartón. Devuelve si lo estaba."""
        for fila in range(5):
            for col in range(5):
                if self.numeros[fila][col] == numero and (fila, col) not in self.marcados:
                    self.marcados.add((fila, col))
                    return True
        return False

    def marcado(self, fila: int, col: int) -> bool:
        return (fila, col) in self.marcados


# -- Patrones de premio ------------------------------------------------------

def _linea_horizontal(fila: int) -> set[tuple[int, int]]:
    return {(fila, c) for c in range(5)}


def _linea_vertical(col: int) -> set[tuple[int, int]]:
    return {(f, col) for f in range(5)}


PATRONES: dict[str, set[tuple[int, int]]] = {
    "linea_h1": _linea_horizontal(0),
    "linea_h2": _linea_horizontal(1),
    "linea_h3": _linea_horizontal(2),
    "linea_h4": _linea_horizontal(3),
    "linea_h5": _linea_horizontal(4),
    "linea_v1": _linea_vertical(0),
    "linea_v2": _linea_vertical(1),
    "linea_v3": _linea_vertical(2),
    "linea_v4": _linea_vertical(3),
    "linea_v5": _linea_vertical(4),
    "diagonal": {(i, i) for i in range(5)},
    "diagonal_inv": {(i, 4 - i) for i in range(5)},
    "esquinas": {(0, 0), (0, 4), (4, 0), (4, 4)},
    "carton_lleno": {(f, c) for f in range(5) for c in range(5)},
}

# El centro libre cuenta para cualquier patrón que lo incluya.
CENTRO = LIBRE


def patron_cumplido(carton: Carton, nombre: str) -> bool:
    """¿Tiene el cartón el patrón completo (con las bolas ya marcadas)?"""
    if nombre not in PATRONES:
        raise ErrorDeBingo(f"No existe el patrón {nombre!r}.")
    return PATRONES[nombre] <= carton.marcados


def patrones_cumplidos(carton: Carton) -> list[str]:
    """Todos los patrones que el cartón ya tiene. Útil para 'bingo' completo."""
    return [n for n in PATRONES if PATRONES[n] <= carton.marcados]


# -- Bombo -------------------------------------------------------------------

class Bombo:
    """Las 75 bolas. Saca sin repetir y avisa cuando se acaban."""

    def __init__(self, generador=None) -> None:
        self.bolas = list(range(1, 76))
        self.sacadas: list[int] = []
        self._azar = generador or secrets.SystemRandom()

    def sacar(self) -> int:
        if not self.bolas:
            raise ErrorDeBingo("El bombo está vacío: ya salieron las 75 bolas.")
        i = self._azar.randrange(len(self.bolas))
        bola = self.bolas.pop(i)
        self.sacadas.append(bola)
        return bola

    def quedan(self) -> int:
        return len(self.bolas)


# -- Generación de cartones --------------------------------------------------

def generar_carton(generador=None, id_: str = "") -> Carton:
    """Crea un cartón válido al azar. Cada columna saca 5 números sin repetir."""
    azar = generador or secrets.SystemRandom()
    columnas: list[list[int]] = []
    for lo, hi in RANGOS:
        disponibles = list(range(lo, hi + 1))
        elegidos: list[int] = []
        for _ in range(5):
            elegidos.append(disponibles.pop(azar.randrange(len(disponibles))))
        columnas.append(elegidos)
    numeros = tuple(tuple(columnas[col][fila] for col in range(5)) for fila in range(5))
    return Carton(numeros=numeros, id=id_ or f"c-{secrets.token_hex(4)}")
