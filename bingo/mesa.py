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
        repartidor=None,
    ) -> None:
        self.sala = sala or Sala()
        self.monedero = monedero or Monedero()
        # Qué parte del bote se lleva el ganador. El resto queda para la casa.
        self.reparto = reparto
        # Cómo se parte el bote de verdad (premio, comisión del anfitrión y app).
        # Si no se pasa, se usa el reparto simple de toda la vida.
        self.repartidor = repartidor

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

    def reparto_de(self, partida_id: str) -> dict:
        """Cómo se parte el bote: premio, comisión del anfitrión y lo de la app.

        Si hay repartidor (salas con dueño), se usa ese; si no, el reparto simple.
        """
        bote = self.sala.bote(partida_id)
        if self.repartidor is not None:
            return self.repartidor(partida_id, bote)
        return {
            "bote": bote,
            "premio": int((Decimal(bote) * self.reparto).quantize(Decimal("1"))),
            "anfitrion": 0,
            "app": bote - int((Decimal(bote) * self.reparto).quantize(Decimal("1"))),
            "con_anfitrion": False,
        }

    def premio_de(self, partida_id: str) -> int:
        """Cuánto se lleva el ganador: el reparto del bote, en céntimos."""
        return self.reparto_de(partida_id)["premio"]

    def resolver_cantada(self, partida_id: str, jugador: str, carton_id: str) -> dict:
        """Valida la cantada y paga el premio. Solo paga si es válida."""
        resultado = self.sala.cantar(partida_id, jugador, carton_id)
        reparto = self.reparto_de(partida_id)
        self.monedero.pagar_premio(jugador, reparto["premio"], motivo=f"bingo {partida_id}")
        # El anfitrión cobra su comisión en el momento, para que no se pierda.
        # Quién cobra lo dice el propio reparto, no un atributo aparte.
        anfitrion = reparto.get("anfitrion_correo", "")
        if reparto["anfitrion"] > 0 and anfitrion:
            self.monedero.pagar_premio(
                anfitrion, reparto["anfitrion"], motivo=f"comisión de sala {partida_id}")
        resultado["premio"] = reparto["premio"]
        resultado["bote"] = reparto["bote"]
        resultado["anfitrion"] = reparto["anfitrion"]
        resultado["app"] = reparto["app"]
        return resultado

    def anfitrion_de(self, partida_id: str) -> str:
        """El correo del anfitrión de la sala de esta partida, si la sala es suya."""
        return self.reparto_de(partida_id).get("anfitrion_correo", "")

    def partida_publica(self, partida_id: str) -> dict:
        """Vista de la partida sin datos privados: sirve para la web."""
        partida = self._partida(partida_id)
        return {
            "id": partida.id,
            "sala": getattr(partida, "sala", ""),
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
