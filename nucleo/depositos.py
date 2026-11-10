"""Depósitos por PayPal y USDT (cripto).

El jugador hace el pago por fuera (desde su PayPal o su billetera) y aquí
**declara** lo que pagó: monto, referencia y día. El dinero NO se acredita solo.

Quién acredita:
- **Glenis IA** deja el depósito en cola, con los datos leídos. No acredita sola.
- **El administrador** confirma. Ahí sí entra el dinero.

Al acreditar, la app retiene de una vez su comisión (10 % por defecto) y le pasa
al jugador el resto. Se hace en el mismo paso del depósito para frenar el lavado
de dinero: quien mete cripto y la saca enseguida ya deja su parte, así que la
app no sirve de puente para mover dinero sucio de un lado a otro.

Tres frenos, porque aquí es donde se pierde el dinero en estas webs:
1. **Una referencia no vale dos veces el mismo día.** Si alguien reenvía la misma
   captura, se rechaza.
2. **Tope diario por jugador.**
3. **No se acredita un depósito de una cuenta que no existe.**
"""

from __future__ import annotations

import os
import re
import secrets
import time
from dataclasses import dataclass, field

from .almacen import Almacen
from .monedero import Monedero
from .money import a_centimos, a_texto

METODOS = ("paypal", "cripto")

# PayPal y USDT no son de banco: no piden banco de la lista.
METODOS_SIN_BANCO = frozenset({"paypal", "cripto"})

# La referencia de un pago de PayPal o de USDT no es solo números: puede traer
# letras y guiones (el id de transacción de PayPal, o el hash de la red).
REFERENCIA_VALIDA = re.compile(r"^[A-Za-z0-9\-]{4,80}$")
FECHA_VALIDA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErrorDeDeposito(ValueError):
    """Depósito no válido."""


@dataclass
class ConfigDeposito:
    minimo: int = 100              # $ 1,00
    tope_diario: int = 200_000     # $ 2.000,00
    dias_atras: int = 3            # cuántos días atrás se admite declarar el pago
    comision_pct: int = 20         # % que retiene la app al acreditar (anti-lavado)


# La comisión anti-lavado se puede ajustar por entorno (0 a 100 %).
def comision_porcentaje() -> int:
    try:
        valor = int(os.environ.get("BINGO_DEPOSITO_COMISION_PCT", "") or 20)
    except ValueError:
        return 20
    return valor if 0 <= valor <= 100 else 20


def reparto_deposito(centimos: int, pct: int) -> tuple[int, int]:
    """Parte un depósito en (comisión de la app, lo que le queda al jugador).

    La comisión se trunca al céntimo y el resto es del jugador, así que nunca se
    pierde un céntimo y la app nunca cobra de más.
    """
    if centimos < 0:
        raise ErrorDeDeposito("El depósito no puede ser negativo.")
    pct = max(0, min(100, int(pct)))
    comision = centimos * pct // 100
    return comision, centimos - comision


@dataclass
class Deposito:
    id: str
    correo: str
    centimos: int
    metodo: str
    referencia: str
    banco: str
    dia: str
    estado: str
    nota: str
    pedido: float
    revisado: float | None = None
    revisado_por: str | None = None
    pais: str = "VE"
    comision: int = 0          # céntimos que se quedó la app al acreditar
    acreditado: int = 0        # céntimos que entraron al saldo del jugador


def _deposito(fila) -> Deposito:
    claves = fila.keys()
    return Deposito(id=fila["id"], correo=fila["correo"], centimos=fila["centimos"],
                    metodo=fila["metodo"], referencia=fila["referencia"], banco=fila["banco"],
                    dia=fila["dia"], estado=fila["estado"], nota=fila["nota"],
                    pedido=fila["pedido"], revisado=fila["revisado"],
                    revisado_por=fila["revisado_por"],
                    pais=fila["pais"] if "pais" in claves else "VE",
                    comision=int(fila["comision"]) if "comision" in claves else 0,
                    acreditado=int(fila["acreditado"]) if "acreditado" in claves else 0)


def hoy() -> str:
    return time.strftime("%Y-%m-%d")


class Depositos:
    def __init__(self, almacen: Almacen, monedero: Monedero,
                 config: ConfigDeposito | None = None) -> None:
        self.almacen = almacen
        self.monedero = monedero
        self.config = config or ConfigDeposito()

    # -- declarar --

    def declarar(self, correo: str, importe: object, referencia: str, banco: str,
                 dia: str, metodo: str = "paypal", nota: str = "",
                 pais: str = "") -> Deposito:
        """El jugador dice que ha pagado. Queda en cola, sin acreditar todavía."""
        correo = (correo or "").strip().lower()
        if not self.almacen.usuario(correo):
            raise ErrorDeDeposito("Esa cuenta no existe.")
        if metodo not in METODOS:
            raise ErrorDeDeposito(f"Método no válido. Los permitidos: {', '.join(METODOS)}.")

        from .paises import a_base, es_pais_valido

        pais = (pais or "").strip().upper()
        if pais and not es_pais_valido(pais):
            raise ErrorDeDeposito("Ese país no está disponible todavía.")
        pais = pais or "VE"

        referencia = (referencia or "").strip()
        if not REFERENCIA_VALIDA.match(referencia):
            raise ErrorDeDeposito("La referencia son de 4 a 80 letras o números (id o hash del pago).")

        dia = (dia or "").strip()
        if not FECHA_VALIDA.match(dia):
            raise ErrorDeDeposito("La fecha del pago tiene que ser AAAA-MM-DD.")
        self._comprobar_fecha(dia)

        try:
            # Todo el dinero es en dólares; no hay conversión.
            centimos = a_base(a_centimos(importe), pais)
        except ValueError as exc:
            raise ErrorDeDeposito(str(exc)) from None
        if centimos < self.config.minimo:
            raise ErrorDeDeposito(f"El depósito mínimo es {a_texto(self.config.minimo)}.")

        desde = time.time() - 86400
        if self.almacen.deposito_hoy(correo, desde) + centimos > self.config.tope_diario:
            raise ErrorDeDeposito("Has alcanzado el tope diario de depósitos.")

        # El freno importante: la misma referencia no vale dos veces ese día.
        if self.almacen.referencia_usada(referencia, dia) is not None:
            raise ErrorDeDeposito(
                "Esa referencia ya está registrada para ese día. "
                "Si crees que es un error, escríbenos."
            )

        deposito = Deposito(id=f"d-{secrets.token_hex(6)}", correo=correo, centimos=centimos,
                            metodo=metodo, referencia=referencia, banco=banco, dia=dia,
                            estado="pendiente", nota=nota, pedido=time.time(),
                            pais=pais or "VE")
        self.almacen.crear_deposito({
            "id": deposito.id, "correo": correo, "centimos": centimos, "metodo": metodo,
            "referencia": referencia, "banco": banco, "dia": dia, "nota": nota,
            "pedido": deposito.pedido, "pais": deposito.pais,
        })
        return deposito

    def _comprobar_fecha(self, dia: str) -> None:
        import datetime

        try:
            fecha = datetime.date.fromisoformat(dia)
        except ValueError:
            raise ErrorDeDeposito("Esa fecha no existe.") from None
        hoy_ = datetime.date.today()
        if fecha > hoy_:
            raise ErrorDeDeposito("La fecha del pago no puede ser futura.")
        if (hoy_ - fecha).days > self.config.dias_atras:
            raise ErrorDeDeposito(
                f"Solo se admiten pagos de los últimos {self.config.dias_atras} días."
            )

    # -- revisar (administración o Glenis) --

    def listar(self, estado: str | None = None, correo: str | None = None) -> list[Deposito]:
        return [_deposito(f) for f in self.almacen.depositos(estado, correo)]

    def pendientes(self) -> list[Deposito]:
        return self.listar(estado="pendiente")

    def acreditar(self, id_: str, admin: str, nota: str = "") -> Deposito:
        """Da el dinero por bueno, retiene la comisión de la app y abona el resto.

        La app se queda su comisión (10 % por defecto) en el mismo paso: así el
        jugador no puede meter dinero y sacarlo entero enseguida, que es el
        agujero por el que se cuela el lavado con cripto.
        """
        fila = self.almacen.deposito(id_)
        if fila is None:
            raise ErrorDeDeposito(f"No existe el depósito {id_!r}.")
        antes = _deposito(fila)
        if antes.estado != "pendiente":
            raise ErrorDeDeposito(f"Ese depósito ya está {antes.estado}.")

        comision, neto = reparto_deposito(antes.centimos, self.config.comision_pct)
        # Primero se marca el depósito con lo retenido y lo abonado; después se
        # abona. Si el abono falla, se deshace la marca para que no quede un
        # depósito acreditado sin dinero.
        if self.almacen.resolver_deposito(id_, "acreditado", time.time(), admin, nota,
                                          comision=comision, acreditado=neto) == 0:
            raise ErrorDeDeposito("Otro administrador se adelantó con ese depósito.")
        try:
            self.monedero.recargar(
                antes.correo, neto,
                f"depósito {antes.referencia} ({antes.banco}); comisión {comision} céntimos")
        except Exception as exc:  # noqa: BLE001
            self.almacen.resolver_deposito(id_, "pendiente", time.time(), admin,
                                           f"falló el abono: {exc}", comision=0, acreditado=0)
            raise ErrorDeDeposito(f"No se pudo abonar: {exc}") from None
        return _deposito(self.almacen.deposito(id_))

    def rechazar(self, id_: str, admin: str, nota: str = "") -> Deposito:
        fila = self.almacen.deposito(id_)
        if fila is None:
            raise ErrorDeDeposito(f"No existe el depósito {id_!r}.")
        antes = _deposito(fila)
        if antes.estado != "pendiente":
            raise ErrorDeDeposito(f"Ese depósito ya está {antes.estado}.")
        if self.almacen.resolver_deposito(id_, "rechazado", time.time(), admin, nota) == 0:
            raise ErrorDeDeposito("Otro administrador se adelantó con ese depósito.")
        return _deposito(self.almacen.deposito(id_))

    def comision_total(self) -> int:
        """Lo que se ha quedado la app con los depósitos acreditados."""
        return sum(d.comision for d in self.listar(estado="acreditado"))

    def total_pendiente(self) -> int:
        return sum(d.centimos for d in self.pendientes())

    def deposito_hoy_de(self, correo: str) -> int:
        return self.almacen.deposito_hoy(correo, time.time() - 86400)
