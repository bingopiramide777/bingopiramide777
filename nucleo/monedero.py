"""Monedero con base de datos: el saldo sobrevive al reinicio.

El monedero trabaja SIEMPRE en céntimos enteros. La conversión desde texto
("10,50") se hace una sola vez, en el borde del sistema (la web), con
`a_centimos`. Aquí dentro no se vuelve a convertir nada.

Cada movimiento se escribe en la base de datos en una transacción junto con el
saldo. O se guardan los dos, o ninguno: nunca un saldo sin su movimiento.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .almacen import Almacen


class ErrorDeMonedero(ValueError):
    """Operación de dinero no permitida."""


@dataclass
class Movimiento:
    id: str
    jugador: str
    tipo: str          # recarga | apuesta | premio | retiro | ajuste | reembolso
    centimos: int      # positivo entra, negativo sale
    saldo_despues: int
    motivo: str = ""
    cuando: float = 0.0


class Monedero:
    def __init__(self, almacen: Almacen) -> None:
        self.almacen = almacen

    # -- consulta --

    def saldo(self, jugador: str) -> int:
        return self.almacen.saldo(jugador)

    def historial(self, jugador: str, limite: int = 200) -> list[Movimiento]:
        return [
            Movimiento(
                id=f["id"], jugador=f["correo"], tipo=f["tipo"], centimos=f["centimos"],
                saldo_despues=f["saldo_despues"], motivo=f["motivo"], cuando=f["cuando"],
            )
            for f in self.almacen.movimientos(jugador, limite)
        ]

    def total_en_cuentas(self) -> int:
        return self.almacen.total_en_cuentas()

    # -- movimientos (todo en céntimos) --

    def recargar(self, jugador: str, centimos: int, motivo: str = "recarga") -> Movimiento:
        return self._mover(jugador, self._entero(centimos), "recarga", motivo)

    def ajustar(self, jugador: str, centimos: int, motivo: str) -> Movimiento:
        """Ajuste a mano (bono, corrección). Puede ser negativo, pero nunca deja
        el saldo por debajo de cero."""
        return self._mover(jugador, self._entero(centimos), "ajuste", motivo)

    def cobrar_apuesta(self, jugador: str, centimos: int, motivo: str = "") -> Movimiento:
        """Saca dinero del saldo para una apuesta. Falla si no llega."""
        return self._mover(jugador, -self._entero(centimos), "apuesta", motivo)

    def pagar_premio(self, jugador: str, centimos: int, motivo: str = "") -> Movimiento:
        return self._mover(jugador, self._entero(centimos), "premio", motivo)

    def retirar(self, jugador: str, centimos: int, motivo: str = "") -> Movimiento:
        return self._mover(jugador, -self._entero(centimos), "retiro", motivo)

    def devolver(self, jugador: str, centimos: int, motivo: str = "") -> Movimiento:
        """Devuelve dinero de un retiro rechazado."""
        return self._mover(jugador, self._entero(centimos), "reembolso", motivo)

    # -- interno --

    @staticmethod
    def _entero(centimos: object) -> int:
        """El monedero solo acepta céntimos enteros. Cualquier otra cosa es un error
        del programa, y se avisa en vez de adivinar."""
        if isinstance(centimos, bool) or not isinstance(centimos, int):
            raise ErrorDeMonedero(
                f"El monedero trabaja en céntimos enteros, y llegó {centimos!r}. "
                "Convierte antes con a_centimos()."
            )
        return centimos

    def _mover(self, jugador: str, centimos: int, tipo: str, motivo: str) -> Movimiento:
        if not jugador:
            raise ErrorDeMonedero("Hace falta un jugador.")
        if centimos == 0:
            raise ErrorDeMonedero("Un movimiento de cero no tiene sentido.")
        mov_id = f"m-{secrets.token_hex(6)}"
        cuando = time.time()
        self.almacen.asegurar_cuenta(jugador)
        try:
            nuevo = self.almacen.aplicar_movimiento(jugador, tipo, centimos, motivo, cuando, mov_id)
        except ValueError as exc:
            raise ErrorDeMonedero(str(exc)) from None
        return Movimiento(id=mov_id, jugador=jugador, tipo=tipo, centimos=centimos,
                          saldo_despues=nuevo, motivo=motivo, cuando=cuando)
