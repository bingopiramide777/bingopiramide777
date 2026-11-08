"""Configuración multi-país de pagos.

Adaptado de ``config/payments.ts``. El dinero se guarda en céntimos enteros: el
país no cambia las cuentas, solo **cómo se muestra** (moneda y símbolo) y **por
dónde se cobra** (Pago Móvil, Nequi, MACH o Cash App).

El país activo vive en una variable de contexto por petición, así ``a_texto``
muestra la moneda correcta sin tener que pasarla por cada llamada.

Los datos de cobro (teléfono, cédula, cashtag) salen de variables de entorno para
poder cambiarlos en Render sin tocar el código. Los valores por defecto son
marcadores de posición: hay que reemplazarlos por los reales.
"""

from __future__ import annotations

import contextvars
import os
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAIS_POR_DEFECTO = "VE"

# La moneda BASE: todo el dinero de dentro (saldos, botes, premios) se guarda en
# céntimos de esta moneda. Los demás países se convierten a/desde ella. Se elige
# Venezuela porque los saldos que ya existen están en bolívares, así la mejora no
# cambia ni un céntimo de lo que la gente ya tiene.
PAIS_BASE = "VE"


# Tasa por defecto: cuántas unidades de la moneda BASE vale 1 unidad de la moneda
# del país. Por ejemplo, US = 40 significa "1 dólar = 40 bolívares".
#
# OJO: son valores de ejemplo. Las tasas reales cambian todos los días y hay que
# ponerlas con las variables BINGO_TASA_CO, BINGO_TASA_CL y BINGO_TASA_US en
# Render. Si no se pone ninguna, valen estos números y los precios saldrán mal.
TASAS_POR_DEFECTO: dict[str, Decimal] = {
    "VE": Decimal("1"),
    "CO": Decimal("0.01"),    # 1 peso = 0,01 Bs
    "CL": Decimal("0.04"),    # 1 peso chileno = 0,04 Bs
    "US": Decimal("40"),      # 1 dólar = 40 Bs
}


@dataclass(frozen=True)
class Pais:
    code: str
    nombre: str
    moneda: str
    simbolo: str
    bandera: str
    locale: str
    # Nombre de la moneda en plural y minúscula, para textos: "bolívares", "pesos".
    moneda_nombre: str = ""

    def a_dict(self) -> dict:
        return {"code": self.code, "name": self.nombre, "currency": self.moneda,
                "currencySymbol": self.simbolo, "flag": self.bandera, "locale": self.locale,
                "currencyName": self.moneda_nombre}


@dataclass(frozen=True)
class CampoPago:
    key: str
    label: str
    placeholder: str
    required: bool = True
    tipo: str = "text"

    def a_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "placeholder": self.placeholder,
                "required": self.required, "type": self.tipo}


@dataclass(frozen=True)
class DatoCuenta:
    label: str
    value: str
    instructions: str = ""

    def a_dict(self) -> dict:
        return {"label": self.label, "value": self.value, "instructions": self.instructions}


@dataclass(frozen=True)
class MetodoPago:
    id: str
    nombre: str
    country: str
    moneda: str
    fields: tuple[CampoPago, ...]
    _cuentas: object  # callable -> tuple[DatoCuenta, ...]

    @property
    def platform_account(self) -> tuple[DatoCuenta, ...]:
        # Se calcula al pedirlo (no al importar) para que los cambios de entorno
        # en Render surtan efecto sin reiniciar el proceso.
        return self._cuentas() if callable(self._cuentas) else tuple(self._cuentas)

    def a_dict(self) -> dict:
        return {"id": self.id, "name": self.nombre, "country": self.country,
                "currency": self.moneda,
                "fields": [f.a_dict() for f in self.fields],
                "platformAccount": [c.a_dict() for c in self.platform_account]}


# ---------------------------------------------------------------------------
# Países soportados
# ---------------------------------------------------------------------------

PAISES: tuple[Pais, ...] = (
    Pais("VE", "Venezuela", "VES", "Bs", "🇻🇪", "es-VE", "bolívares"),
    Pais("CO", "Colombia", "COP", "$", "🇨🇴", "es-CO", "pesos"),
    Pais("CL", "Chile", "CLP", "$", "🇨🇱", "es-CL", "pesos"),
    Pais("US", "Estados Unidos", "USD", "$", "🇺🇸", "en-US", "dólares"),
)

# Código de país que devuelve el detector de IP -> nuestro código.
IP_COUNTRY_MAP: dict[str, str] = {"VE": "VE", "CO": "CO", "CL": "CL", "US": "US"}


def _env(clave: str, por_defecto: str) -> str:
    return os.environ.get(clave) or por_defecto


def _cuenta_venezuela() -> tuple[DatoCuenta, ...]:
    """La cuenta de Pago Móvil. Reutiliza la que ya usa el módulo de depósitos."""
    from .depositos import CuentaDePago

    c = CuentaDePago.desde_entorno()
    datos = [DatoCuenta("Banco", c.banco, "Realiza el Pago Móvil a los siguientes datos"),
             DatoCuenta("Teléfono", c.telefono)]
    if c.cedula:
        datos.append(DatoCuenta("Cédula / RIF", c.cedula))
    if c.titular:
        datos.append(DatoCuenta("Titular", c.titular))
    return tuple(datos)


# ---------------------------------------------------------------------------
# Métodos de pago por país
# ---------------------------------------------------------------------------

def _cuenta_colombia() -> tuple[DatoCuenta, ...]:
    return (DatoCuenta("Número Nequi", _env("BINGO_PAGO_NEQUI_TELEFONO", "3000000000"),
                       "Envía el dinero a este número de Nequi"),)


def _cuenta_chile() -> tuple[DatoCuenta, ...]:
    return (DatoCuenta("Número MACH", _env("BINGO_PAGO_MACH_TELEFONO", "900000000"),
                       "Envía el dinero a este número de MACH"),)


def _cuenta_estados_unidos() -> tuple[DatoCuenta, ...]:
    return (DatoCuenta("Cash App", _env("BINGO_PAGO_CASHAPP_CASHTAG", "$TuCashtag"),
                       "Envía el dinero a este $Cashtag de Cash App"),)


def _cuenta_wise() -> tuple[DatoCuenta, ...]:
    return (
        DatoCuenta("Tipo de cuenta", _env("BINGO_PAGO_WISE_TIPO", "Checking"),
                   "Solo se usa para transferencias nacionales"),
        DatoCuenta("Número de ruta (para wire y ACH)", _env("BINGO_PAGO_WISE_RUTA", "Por configurar"),
                   "Proporcionado a Wise por Lead Bank, nuestro socio"),
        DatoCuenta("Número de cuenta", _env("BINGO_PAGO_WISE_CUENTA", "Por configurar"),
                   "Envía el dinero a esta cuenta de Wise"),
    )


METODOS_PAGO: tuple[MetodoPago, ...] = (
    MetodoPago(
        id="pago_movil_ve", nombre="Pago Móvil", country="VE", moneda="VES",
        fields=(
            CampoPago("phone", "Número de teléfono", "04141234567", True, "tel"),
            CampoPago("cedula", "Cédula de identidad", "V-12345678", True, "text"),
        ),
        _cuentas=_cuenta_venezuela,
    ),
    MetodoPago(
        id="nequi_co", nombre="Nequi", country="CO", moneda="COP",
        fields=(
            CampoPago("phone", "Número de Nequi", "3001234567", True, "tel"),
        ),
        _cuentas=_cuenta_colombia,
    ),
    MetodoPago(
        id="mach_cl", nombre="MACH", country="CL", moneda="CLP",
        fields=(
            CampoPago("phone", "Número de teléfono MACH", "912345678", True, "tel"),
            CampoPago("rut", "RUT (recomendado)", "12.345.678-9", False, "text"),
        ),
        _cuentas=_cuenta_chile,
    ),
    MetodoPago(
        id="cashapp_us", nombre="Cash App", country="US", moneda="USD",
        fields=(
            CampoPago("cashtag", "$Cashtag o teléfono", "$tuusuario o +1234567890", True, "text"),
        ),
        _cuentas=_cuenta_estados_unidos,
    ),
    MetodoPago(
        id="wise_us", nombre="Wise", country="US", moneda="USD",
        fields=(
            CampoPago("correo", "Correo de Wise", "tu@correo.com", True, "email"),
            CampoPago("titular", "Nombre del titular", "Nombre y apellido", True, "text"),
        ),
        _cuentas=_cuenta_wise,
    ),
)

IDS_METODOS_PAGO: tuple[str, ...] = tuple(m.id for m in METODOS_PAGO)

# Métodos que no se apoyan en un banco (se cobran por teléfono o cashtag).
METODOS_SIN_BANCO: frozenset[str] = frozenset(IDS_METODOS_PAGO)


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def pais(code: str | None) -> Pais | None:
    if not code:
        return None
    code = str(code).strip().upper()
    return next((p for p in PAISES if p.code == code), None)


def es_pais_valido(code: str | None) -> bool:
    return pais(code) is not None


def metodo_de_pais(code: str | None) -> MetodoPago | None:
    if not code:
        return None
    code = str(code).strip().upper()
    return next((m for m in METODOS_PAGO if m.country == code), None)


def metodos_de_pais(code: str | None) -> list[MetodoPago]:
    """Todos los métodos de cobro de un país (EE. UU. tiene Cash App y Wise)."""
    if not code:
        return []
    code = str(code).strip().upper()
    return [m for m in METODOS_PAGO if m.country == code]


def metodo_por_id(id_: str | None) -> MetodoPago | None:
    if not id_:
        return None
    return next((m for m in METODOS_PAGO if m.id == id_), None)


def moneda_de(code: str | None) -> str:
    p = pais(code) or pais(PAIS_POR_DEFECTO)
    return p.moneda


def simbolo_de(code: str | None) -> str:
    p = pais(code) or pais(PAIS_POR_DEFECTO)
    return p.simbolo


def formatear(centimos: int, code: str | None = PAIS_POR_DEFECTO) -> str:
    """Formatea céntimos como 'Bs 1.234,50' o '$ 1.234,50' según el país."""
    if not isinstance(centimos, int):
        raise ValueError("Los céntimos deben ser enteros.")
    simbolo = simbolo_de(code)
    negativo = centimos < 0
    entero, resto = divmod(abs(centimos), 100)
    miles = f"{entero:,}".replace(",", ".")
    return f"{'-' if negativo else ''}{simbolo} {miles},{resto:02d}"


def catalogo() -> dict:
    """Todo el catálogo para el frontend: países y métodos con sus cuentas."""
    return {
        "paises": [p.a_dict() for p in PAISES],
        "metodos_pago": [m.a_dict() for m in METODOS_PAGO],
        "pais_por_defecto": PAIS_POR_DEFECTO,
        "pais_actual": pais_actual(),
    }


# ---------------------------------------------------------------------------
# País activo de la petición
# ---------------------------------------------------------------------------

_pais_actual: contextvars.ContextVar[str] = contextvars.ContextVar(
    "pais_actual", default=PAIS_POR_DEFECTO)


def pais_actual() -> str:
    return _pais_actual.get()


def usar_pais(code: str | None) -> str:
    """Fija el país de la petición actual. Devuelve el país que quedó puesto."""
    elegido = code if es_pais_valido(code) else PAIS_POR_DEFECTO
    _pais_actual.set(elegido)
    return elegido


def simbolo_actual() -> str:
    return simbolo_de(pais_actual())


# ---------------------------------------------------------------------------
# Conversión de moneda
# ---------------------------------------------------------------------------
#
# Todo el dinero de dentro (saldos, botes, premios, retiros) se guarda en
# céntimos de la moneda BASE (bolívares). Cuando un jugador de otro país entra,
# se convierte:
#
#   importe_en_base = importe_local * tasa             (al entrar dinero)
#   importe_local   = importe_en_base / tasa           (al mostrar / al pagar)
#
# La tasa dice cuántas unidades de la moneda base vale 1 unidad local. Así la
# contabilidad interna es única y cuadra siempre, y el jugador ve su moneda.


def tasa_de(code: str | None) -> Decimal:
    """Cuántas unidades de la moneda base vale 1 unidad del país indicado.

    Se lee de las variables de entorno (BINGO_TASA_XX) para poder cambiar las
    tasas en Render sin desplegar. Venezuela es siempre 1: es la moneda base.
    """
    code = (code or PAIS_BASE).strip().upper()
    if code == PAIS_BASE:
        return Decimal("1")
    if not es_pais_valido(code):
        return Decimal("1")
    crudo = os.environ.get(f"BINGO_TASA_{code}")
    if crudo:
        try:
            valor = Decimal(str(crudo).replace(",", "."))
            if valor.is_finite() and valor > 0:
                return valor
        except (InvalidOperation, ValueError):
            pass
    return TASAS_POR_DEFECTO.get(code, Decimal("1"))


def a_base(centimos_locales: int, code: str | None) -> int:
    """Pasa un importe en céntimos del país a céntimos de la moneda base."""
    if not isinstance(centimos_locales, int):
        raise ValueError("Los céntimos deben ser enteros.")
    tasa = tasa_de(code)
    if tasa == 1:
        return centimos_locales
    return int((Decimal(centimos_locales) * tasa).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def de_base(centimos_base: int, code: str | None) -> int:
    """Pasa un importe en céntimos de la moneda base a céntimos del país."""
    if not isinstance(centimos_base, int):
        raise ValueError("Los céntimos deben ser enteros.")
    tasa = tasa_de(code)
    if tasa == 1:
        return centimos_base
    return int((Decimal(centimos_base) / tasa).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def formatear_local(centimos_base: int, code: str | None) -> str:
    """Formatea un importe de la base como texto en la moneda del país indicado."""
    local = de_base(centimos_base, code)
    from .money import a_texto as _a_texto

    return _a_texto(local, simbolo_de(code))


def tasas() -> dict[str, str]:
    """Todas las tasas vigentes, para mostrarlas o depurarlas."""
    return {p.code: str(tasa_de(p.code)) for p in PAISES}


# ---------------------------------------------------------------------------
# Cuentas de cobro del administrador, por país
# ---------------------------------------------------------------------------
#
# La ganancia de la app se cobra en la cuenta que corresponda al país donde se
# jugó. Cada país tiene la suya y se configura por variables de entorno, para
# poder cambiarla en Render sin tocar el código.
#
# Los números de cuenta NO viven en el repositorio: se ponen en Render con
# `sync: false`. Aquí solo queda la forma (qué datos pide cada país) y el
# marcador de posición, para que el panel avise de lo que falta.


@dataclass(frozen=True)
class LineaCuenta:
    label: str
    valor: str

    def a_dict(self) -> dict:
        return {"label": self.label, "value": self.valor}


@dataclass(frozen=True)
class CuentaAdmin:
    pais: str
    banco: str
    titular: str
    moneda: str
    lineas: tuple[LineaCuenta, ...] = ()

    @property
    def configurada(self) -> bool:
        """True si ya se puso una cuenta de verdad (no el marcador de posición)."""
        return bool(self.lineas) and all(l.valor and l.valor != "Por configurar"
                                         for l in self.lineas)

    def a_dict(self) -> dict:
        return {"pais": self.pais, "banco": self.banco, "titular": self.titular,
                "moneda": self.moneda, "simbolo": simbolo_de(self.pais),
                "lineas": [l.a_dict() for l in self.lineas], "configurada": self.configurada}


# Qué datos de cuenta pide cada país, además del banco/entidad y el titular.
_FORMAS_ADMIN: dict[str, tuple[str, ...]] = {
    "VE": ("Teléfono", "Cédula / RIF"),
    "CO": ("Número de cuenta",),
    "CL": ("Número de cuenta", "RUT"),
    "US": ("Tipo de cuenta", "Número de ruta (para wire y ACH)", "Número de cuenta"),
}


def _lineas_admin(code: str) -> tuple[LineaCuenta, ...]:
    """Los datos de la cuenta de administración de un país, leídos del entorno."""
    forma = _FORMAS_ADMIN.get(code, ("Número de cuenta",))
    return tuple(
        LineaCuenta(etiqueta, _env(f"BINGO_ADMIN_CUENTA_{code}_DATO{i + 1}", "Por configurar"))
        for i, etiqueta in enumerate(forma)
    )


def cuenta_admin(code: str) -> CuentaAdmin:
    """La cuenta donde se cobra la ganancia de la app en un país."""
    code = (code or PAIS_POR_DEFECTO).strip().upper()
    if not es_pais_valido(code):
        code = PAIS_POR_DEFECTO
    return CuentaAdmin(
        pais=code,
        banco=_env(f"BINGO_ADMIN_CUENTA_{code}_BANCO", "Por configurar"),
        titular=_env(f"BINGO_ADMIN_CUENTA_{code}_TITULAR", "BingoPiramide777"),
        moneda=moneda_de(code),
        lineas=_lineas_admin(code),
    )


def cuentas_admin() -> list[CuentaAdmin]:
    return [cuenta_admin(p.code) for p in PAISES]
