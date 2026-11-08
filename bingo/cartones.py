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
    "cuatro_esquinas": {(0, 0), (0, 4), (4, 0), (4, 4)},
    # Cruz grande: toda la fila y la columna del centro (9 casillas).
    "cruz_grande": ({(2, c) for c in range(5)} | {(f, 2) for f in range(5)}),
    # Cruz pequeña: el centro y sus cuatro vecinos (5 casillas).
    "cruz_pequena": {(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)},
    "carton_lleno": {(f, c) for f in range(5) for c in range(5)},
}

# Tipos de juego (modalidades) que la administración puede poner en una sala,
# como en Juegoactivo: Línea, Columna, Diagonal, 4 Esquinas, Cruz Grande, Cruz
# Pequeña y Cartón Lleno. Cada uno premia un patrón del cartón.
TIPOS_JUEGO: tuple[tuple[str, str], ...] = (
    ("linea_h1", "Línea"),
    ("linea_v1", "Columna"),
    ("diagonal", "Diagonal"),
    ("cuatro_esquinas", "Cuatro esquinas"),
    ("cruz_grande", "Cruz grande"),
    ("cruz_pequena", "Cruz pequeña"),
    ("carton_lleno", "Cartón lleno"),
)

NOMBRE_TIPO_JUEGO: dict[str, str] = dict(TIPOS_JUEGO)

# El centro libre cuenta para cualquier patrón que lo incluya.
CENTRO = LIBRE

# Modos de juego, como en Juegoactivo: Normal, Cartón Lleno y Competencia.
# Cada modo admite unos patrones. Cuantos más patrones, antes se canta bingo.
MODOS: dict[str, tuple[str, ...]] = {
    # Normal: una línea, columna o diagonal. El bingo de siempre.
    "normal": ("linea_h1", "linea_h2", "linea_h3", "linea_h4", "linea_h5",
               "linea_v1", "linea_v2", "linea_v3", "linea_v4", "linea_v5",
               "diagonal", "diagonal_inv"),
    # Cartón lleno: hay que completar los 25 números. La partida más larga.
    "carton_lleno": ("carton_lleno",),
    # Competencia: además de líneas y diagonales valen las esquinas, así que
    # salta antes. Partidas rápidas.
    "competencia": ("linea_h1", "linea_h2", "linea_h3", "linea_h4", "linea_h5",
                    "linea_v1", "linea_v2", "linea_v3", "linea_v4", "linea_v5",
                    "diagonal", "diagonal_inv", "esquinas"),
}


def patrones_del_modo(modo: str) -> tuple[str, ...]:
    """Patrones que valen en un modo de juego."""
    try:
        return MODOS[modo]
    except KeyError:
        raise ErrorDeBingo(f"No existe el modo de juego {modo!r}.") from None


def patron_cumplido(carton: Carton, nombre: str) -> bool:
    """¿Tiene el cartón el patrón completo (con las bolas ya marcadas)?"""
    if nombre not in PATRONES:
        raise ErrorDeBingo(f"No existe el patrón {nombre!r}.")
    return PATRONES[nombre] <= carton.marcados


def patrones_cumplidos(carton: Carton) -> list[str]:
    """Todos los patrones que el cartón ya tiene. Útil para 'bingo' completo."""
    return [n for n in PATRONES if PATRONES[n] <= carton.marcados]


def fichas_que_faltan(carton: Carton, patrones: tuple[str, ...] | list[str]) -> int:
    """Cuántas casillas le faltan al cartón para cantar, con el mejor patrón.

    Es la transparencia del juego: cualquier jugador puede ver en vivo a cuánto
    está cada oponente. Se cuenta sobre el patrón más cercano de los que valen
    en la partida. Devuelve 0 si ya lo tiene.
    """
    mejor = None
    for nombre in patrones:
        casillas = PATRONES.get(nombre)
        if casillas is None:
            raise ErrorDeBingo(f"No existe el patrón {nombre!r}.")
        faltan = len(casillas - carton.marcados)
        if mejor is None or faltan < mejor:
            mejor = faltan
            if mejor == 0:
                break
    return mejor if mejor is not None else 0


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
