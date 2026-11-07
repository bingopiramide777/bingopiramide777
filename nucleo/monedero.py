"""Monedero: saldo, recargas, retiros y pago de premios.

Todo movimiento se registra con su motivo. El saldo nunca se toca directamente
desde fuera: se entra por recargar/apostar/pagar/retirar, y cada una deja rastro.
Un saldo negativo es un error del programa, no un estado válido.

El monedero trabaja SIEMPRE en céntimos enteros. La conversión desde texto
("10,50") se hace una sola vez, en el borde del sistema (la web), con
`a_centimos`. Aquí dentro no se vuelve a convertir nada: así no hay forma de
multiplicar por 100 dos veces por descuido.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

class ErrorDeMonedero(ValueError):
    """Operación de dinero no permitida."""


@dataclass
class Movimiento:
    id: str
    jugador: str
    tipo: str          # recarga | apuesta | premio | retiro | ajuste
    centimos: int      # positivo entra, negativo sale
    saldo_despues: int
    motivo: str = ""
    cuando: float = field(default_factory=time.time)


@dataclass
class Cuenta:
    jugador: str
    centimos: int = 0


class Monedero:
    def __init__(self) -> None:
        self.cuentas: dict[str, Cuenta] = {}
        self.movimientos: list[Movimiento] = []

    # -- consulta --

    def cuenta(self, jugador: str) -> Cuenta:
        return self.cuentas.setdefault(jugador, Cuenta(jugador=jugador))

    def saldo(self, jugador: str) -> int:
        return self.cuenta(jugador).centimos

    def historial(self, jugador: str) -> list[Movimiento]:
        return [m for m in self.movimientos if m.jugador == jugador]

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
        cuenta = self.cuenta(jugador)
        nuevo = cuenta.centimos + centimos
        if nuevo < 0:
            raise ErrorDeMonedero(
                f"Saldo insuficiente: hay {cuenta.centimos} céntimos y se intentan mover {centimos}."
            )
        cuenta.centimos = nuevo
        mov = Movimiento(
            id=f"m-{secrets.token_hex(6)}",
            jugador=jugador,
            tipo=tipo,
            centimos=centimos,
            saldo_despues=nuevo,
            motivo=motivo,
        )
        self.movimientos.append(mov)
        return mov
