"""Retiros: el jugador pide, el administrador paga o rechaza.

Regla de oro: el dinero se descuenta al PEDIR. Así el jugador no puede pedir dos
veces el mismo saldo. Si se rechaza, se devuelve. Pagar no vuelve a mover el
saldo: solo marca el retiro como completado.

La idempotencia la da la base de datos: `resolver_retiro` solo cambia filas que
siguen en 'pendiente'. Si dos administradores pulsan a la vez, solo uno cobra.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .almacen import Almacen
from .monedero import ErrorDeMonedero, Monedero
from .money import a_centimos, a_texto

METODOS = ("paypal", "cripto")


class ErrorDeRetiro(ValueError):
    """Retiro no permitido."""


@dataclass
class ConfigRetiro:
    minimo: int = 100            # $ 1,00
    tope_diario: int = 200_000   # $ 2.000,00
    metodos: tuple[str, ...] = METODOS


@dataclass
class Retiro:
    id: str
    correo: str
    centimos: int
    metodo: str
    detalles: str
    estado: str
    pedido: float
    revisado: float | None = None
    revisado_por: str | None = None
    nota: str = ""


def _retiro(fila) -> Retiro:
    return Retiro(id=fila["id"], correo=fila["correo"], centimos=fila["centimos"],
                  metodo=fila["metodo"], detalles=fila["detalles"], estado=fila["estado"],
                  pedido=fila["pedido"], revisado=fila["revisado"],
                  revisado_por=fila["revisado_por"], nota=fila["nota"])


class Retiros:
    def __init__(self, almacen: Almacen, monedero: Monedero,
                 config: ConfigRetiro | None = None) -> None:
        self.almacen = almacen
        self.monedero = monedero
        self.config = config or ConfigRetiro()

    def pedir(self, correo: str, importe: object, metodo: str, detalles: str) -> Retiro:
        if metodo not in self.config.metodos:
            raise ErrorDeRetiro(f"Método no válido. Los permitidos son: {', '.join(self.config.metodos)}.")
        detalles = (detalles or "").strip()
        if len(detalles) < 5:
            raise ErrorDeRetiro("Hacen falta los datos de cobro (cuenta, teléfono o correo).")
        try:
            # El importe lo pide el jugador en su moneda; dentro se guarda en la base.
            from .paises import a_base, pais_actual

            centimos = a_base(a_centimos(importe), pais_actual())
        except ValueError as exc:
            raise ErrorDeRetiro(str(exc)) from None
        if centimos <= 0:
            raise ErrorDeRetiro("El importe tiene que ser mayor que cero.")
        if centimos < self.config.minimo:
            raise ErrorDeRetiro(
                f"El mínimo para retirar es {a_texto(self.config.minimo)}."
            )
        # El tope diario cuenta lo pedido hoy, sin contar lo rechazado.
        desde = time.time() - 86400
        if self.almacen.retirado_hoy(correo, desde) + centimos > self.config.tope_diario:
            raise ErrorDeRetiro("Has alcanzado el tope diario de retiros.")
        if self.monedero.saldo(correo) < centimos:
            raise ErrorDeRetiro("No tienes saldo suficiente para ese retiro.")

        retiro = Retiro(id=f"r-{secrets.token_hex(6)}", correo=correo, centimos=centimos,
                        metodo=metodo, detalles=detalles, estado="pendiente", pedido=time.time())
        # Primero se descuenta el saldo; después se anota el retiro. Si el
        # descuento falla, no queda un retiro sin respaldo.
        self.monedero.retirar(correo, centimos, f"retiro {retiro.id}")
        self.almacen.crear_retiro({
            "id": retiro.id, "correo": correo, "centimos": centimos,
            "metodo": metodo, "detalles": detalles, "pedido": retiro.pedido,
        })
        return retiro

    def listar(self, estado: str | None = None, correo: str | None = None) -> list[Retiro]:
        return [_retiro(f) for f in self.almacen.retiros(estado, correo)]

    def pendientes(self) -> list[Retiro]:
        return self.listar(estado="pendiente")

    def pagar(self, id_: str, admin: str, nota: str = "") -> Retiro:
        """Marca el retiro como pagado. No mueve saldo: ya se descontó al pedir."""
        return self._resolver(id_, "pagado", admin, nota)

    def rechazar(self, id_: str, admin: str, nota: str = "") -> Retiro:
        """Rechaza el retiro y DEVUELVE el dinero al jugador."""
        retiro = self._resolver(id_, "rechazado", admin, nota, devolver=True)
        return retiro

    def _resolver(self, id_: str, estado: str, admin: str, nota: str, devolver: bool = False) -> Retiro:
        fila = self.almacen.retiro(id_)
        if fila is None:
            raise ErrorDeRetiro(f"No existe el retiro {id_!r}.")
        fila_antes = _retiro(fila)
        if fila_antes.estado != "pendiente":
            raise ErrorDeRetiro(f"Ese retiro ya está {fila_antes.estado}.")
        cambiadas = self.almacen.resolver_retiro(id_, estado, time.time(), admin, nota)
        if cambiadas == 0:
            raise ErrorDeRetiro("Otro administrador se adelantó: ese retiro ya se resolvió.")
        if devolver:
            try:
                self.monedero.devolver(fila_antes.correo, fila_antes.centimos,
                                       f"devolución retiro {id_}")
            except ErrorDeMonedero as exc:  # no debería pasar: el saldo era suyo
                raise ErrorDeRetiro(f"El retiro se rechazó pero falló la devolución: {exc}") from None
        return _retiro(self.almacen.retiro(id_))

    def total_pendiente(self) -> int:
        return sum(r.centimos for r in self.pendientes())
