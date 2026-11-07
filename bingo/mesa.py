"""Mesa de bingo: une la sala con el monedero.

Único punto donde se cobran cartones y se pagan premios. Si el cobro falla, el
cartón se devuelve: nunca queda un cartón vendido sin haber cobrado.
"""

from __future__ import annotations

from decimal import Decimal

from nucleo.monedero import ErrorDeMonedero, Monedero

from .sala import ErrorDeSala, Partida, Sala


class ErrorDeMesaBingo(ValueError):
    """La operación de la mesa no se pudo completar entera."""


class MesaBingo:
    def __init__(
        self,
        sala: Sala | None = None,
        monedero: Monedero | None = None,
        reparto: Decimal = Decimal("0.80"),
    ) -> None:
        self.sala = sala or Sala()
        self.monedero = monedero or Monedero()
        # Qué parte del bote se lleva el ganador. El resto queda para la casa.
        self.reparto = reparto

    def comprar_carton(self, partida_id: str, jugador: str) -> tuple[str, int]:
        """Cobra el cartón y lo entrega. O las dos cosas, o ninguna."""
        carton, precio = self.sala.comprar_carton(partida_id, jugador)
        try:
            self.monedero.cobrar_apuesta(jugador, precio, motivo=f"cartón {partida_id}")
        except ErrorDeMonedero as exc:
            # Devolvemos el cartón: no puede quedar vendido sin cobrar.
            partida = self.sala.partidas[partida_id]
            partida.cartones.pop(carton.id, None)
            partida.dueno.pop(carton.id, None)
            raise ErrorDeMesaBingo(str(exc)) from None
        return carton.id, precio

    def premio_de(self, partida_id: str) -> int:
        """Cuánto se lleva el ganador: el reparto del bote, en céntimos."""
        bote = self.sala.bote(partida_id)
        return int((Decimal(bote) * self.reparto).quantize(Decimal("1")))

    def resolver_cantada(self, partida_id: str, jugador: str, carton_id: str) -> dict:
        """Valida la cantada y paga el premio. Solo paga si es válida."""
        resultado = self.sala.cantar(partida_id, jugador, carton_id)
        premio = self.premio_de(partida_id)
        self.monedero.pagar_premio(jugador, premio, motivo=f"bingo {partida_id}")
        resultado["premio"] = premio
        resultado["bote"] = self.sala.bote(partida_id)
        return resultado

    def partida_publica(self, partida_id: str) -> dict:
        """Vista de la partida sin datos privados: sirve para la web."""
        partida = self._partida(partida_id)
        return {
            "id": partida.id,
            "patron": partida.patron,
            "estado": partida.estado,
            "precio_carton": partida.precio_carton,
            "cartones": len(partida.cartones),
            "bolas_sacadas": list(partida.bombo.sacadas),
            "ganador": partida.ganador,
        }

    def _partida(self, partida_id: str) -> Partida:
        try:
            return self.sala.partidas[partida_id]
        except KeyError:
            raise ErrorDeMesaBingo(f"No existe la partida {partida_id!r}.") from None
