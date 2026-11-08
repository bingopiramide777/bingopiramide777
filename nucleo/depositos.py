"""Depósitos por Pago Móvil y transferencia, como en Juegoactivo.

El jugador hace el pago por fuera (desde su banco), y aquí **declara** lo que
pagó: monto, referencia, banco y día. El dinero NO se acredita solo.

Quién acredita:
- **Glenis IA** deja el depósito en cola, con los datos leídos. No acredita sola.
- **El administrador** confirma. Ahí sí entra el dinero.

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

METODOS = ("pago_movil", "transferencia", "nequi", "mach", "cashapp", "wise")

# Los métodos que no son de banco no piden banco: se cobran por teléfono/cashtag.
METODOS_SIN_BANCO = frozenset({"nequi", "mach", "cashapp", "wise"})

# Cuenta a la que el jugador manda el dinero. Los datos del Pago Móvil van aquí
# y no repartidos por el código, para poder cambiarlos desde Render sin desplegar.
@dataclass
class CuentaDePago:
    banco: str = "Banco de Venezuela"
    telefono: str = "0416-7677264"
    cedula: str = "12.256.618"
    titular: str = ""

    @classmethod
    def desde_entorno(cls) -> "CuentaDePago":
        # Si la variable no está puesta, vale el valor por defecto de arriba.
        base = cls()
        return cls(
            banco=os.environ.get("BINGO_PAGO_BANCO") or base.banco,
            telefono=os.environ.get("BINGO_PAGO_TELEFONO") or base.telefono,
            cedula=os.environ.get("BINGO_PAGO_CEDULA") or base.cedula,
            titular=os.environ.get("BINGO_PAGO_TITULAR") or base.titular,
        )

    @property
    def configurada(self) -> bool:
        return bool(self.telefono or self.cedula)

    def a_dict(self) -> dict:
        return {"banco": self.banco, "telefono": self.telefono,
                "cedula": self.cedula, "titular": self.titular,
                "configurada": self.configurada}


BANCOS = (
    "Banco de Venezuela", "Banesco", "Mercantil", "BBVA Provincial", "Banco Nacional de Crédito",
    "Bancaribe", "Banco Exterior", "Banco del Tesoro", "Banco Bicentenario", "Banco Plaza",
    "Banco Sofitasa", "Banco Fondo Común", "Banco Activo", "Banco Caroní", "Banco del Sur",
    "Otro",
)

# Una referencia bancaria venezolana suele ser un número de 4 a 20 dígitos.
REFERENCIA_VALIDA = re.compile(r"^\d{4,20}$")
FECHA_VALIDA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErrorDeDeposito(ValueError):
    """Depósito no válido."""


@dataclass
class ConfigDeposito:
    minimo: int = 1_000            # Bs 10,00
    tope_diario: int = 2_000_000   # Bs 20.000,00
    dias_atras: int = 3            # cuántos días atrás se admite declarar el pago
    cuenta: CuentaDePago = field(default_factory=CuentaDePago.desde_entorno)


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


def _deposito(fila) -> Deposito:
    claves = fila.keys()
    return Deposito(id=fila["id"], correo=fila["correo"], centimos=fila["centimos"],
                    metodo=fila["metodo"], referencia=fila["referencia"], banco=fila["banco"],
                    dia=fila["dia"], estado=fila["estado"], nota=fila["nota"],
                    pedido=fila["pedido"], revisado=fila["revisado"],
                    revisado_por=fila["revisado_por"],
                    pais=fila["pais"] if "pais" in claves else "VE")


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
                 dia: str, metodo: str = "pago_movil", nota: str = "",
                 pais: str = "") -> Deposito:
        """El jugador dice que ha pagado. Queda en cola, sin acreditar todavía."""
        correo = (correo or "").strip().lower()
        if not self.almacen.usuario(correo):
            raise ErrorDeDeposito("Esa cuenta no existe.")
        if metodo not in METODOS:
            raise ErrorDeDeposito(f"Método no válido. Los permitidos: {', '.join(METODOS)}.")
        banco = (banco or "").strip()
        # Los métodos de banco (Pago Móvil, transferencia) exigen banco de la lista.
        # Los de teléfono/cashtag (Nequi, MACH, Cash App, Wise) no lo usan.
        if metodo not in METODOS_SIN_BANCO:
            if banco not in BANCOS:
                raise ErrorDeDeposito("Ese banco no está en la lista.")

        from .paises import a_base, es_pais_valido

        pais = (pais or "").strip().upper()
        if pais and not es_pais_valido(pais):
            raise ErrorDeDeposito("Ese país no está disponible todavía.")
        pais = pais or "VE"

        referencia = (referencia or "").strip()
        if not REFERENCIA_VALIDA.match(referencia):
            raise ErrorDeDeposito("La referencia son solo números (entre 4 y 20 cifras).")

        dia = (dia or "").strip()
        if not FECHA_VALIDA.match(dia):
            raise ErrorDeDeposito("La fecha del pago tiene que ser AAAA-MM-DD.")
        self._comprobar_fecha(dia)

        try:
            # El importe llega en la moneda del país del jugador; dentro se guarda
            # en la moneda base, para que la contabilidad sea una sola.
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
        """Da el dinero por bueno y lo suma al saldo. Solo se puede hacer una vez."""
        return self._resolver(id_, "acreditado", admin, nota, acreditar=True)

    def rechazar(self, id_: str, admin: str, nota: str = "") -> Deposito:
        return self._resolver(id_, "rechazado", admin, nota)

    def _resolver(self, id_: str, estado: str, admin: str, nota: str,
                  acreditar: bool = False) -> Deposito:
        fila = self.almacen.deposito(id_)
        if fila is None:
            raise ErrorDeDeposito(f"No existe el depósito {id_!r}.")
        antes = _deposito(fila)
        if antes.estado != "pendiente":
            raise ErrorDeDeposito(f"Ese depósito ya está {antes.estado}.")

        # Primero se marca el depósito; después se abona. Si el abono falla, se
        # deshace la marca para que no quede un depósito acreditado sin dinero.
        if self.almacen.resolver_deposito(id_, estado, time.time(), admin, nota) == 0:
            raise ErrorDeDeposito("Otro administrador se adelantó con ese depósito.")

        if acreditar:
            try:
                self.monedero.recargar(antes.correo, antes.centimos,
                                       f"depósito {antes.referencia} ({antes.banco})")
            except Exception as exc:  # noqa: BLE001
                self.almacen.resolver_deposito(id_, "pendiente", time.time(), admin,
                                               f"falló el abono: {exc}")
                raise ErrorDeDeposito(f"No se pudo abonar: {exc}") from None
        return _deposito(self.almacen.deposito(id_))

    def total_pendiente(self) -> int:
        return sum(d.centimos for d in self.pendientes())

    def deposito_hoy_de(self, correo: str) -> int:
        return self.almacen.deposito_hoy(correo, time.time() - 86400)
