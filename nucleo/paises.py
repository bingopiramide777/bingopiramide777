"""Configuración multi-país de pagos.

El dinero se guarda en céntimos enteros y en una sola moneda: el dólar. El país
ya no cambia la moneda; solo **cómo se muestra** (nombre y símbolo) y el idioma.
Se cobra siempre igual en todo el mundo: **PayPal o USDT (cripto)**.

El país activo vive en una variable de contexto por petición, así ``a_texto``
muestra la moneda correcta sin tener que pasarla por cada llamada.

La cuenta de la casa (PayPal y billetera USDT) sale de variables de entorno para
poder cambiarla en Render sin tocar el código.
"""

from __future__ import annotations

import contextvars
import os
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

PAIS_POR_DEFECTO = "VE"

# Una sola moneda para todos: el dólar. Los países se mantienen solo para el
# idioma y la bandera; el dinero es siempre en dólares y no hay conversión.
PAIS_BASE = "US"


# Todo el dinero está en dólares, así que la tasa es siempre 1: no se convierte
# nada. Se deja la función para no tocar a quien la llama.
TASAS_POR_DEFECTO: dict[str, Decimal] = {
    "VE": Decimal("1"),
    "CO": Decimal("1"),
    "CL": Decimal("1"),
    "US": Decimal("1"),
}


@dataclass(frozen=True)
class Pais:
    code: str
    nombre: str
    moneda: str
    simbolo: str
    bandera: str
    locale: str
    # Nombre de la moneda en plural y minúscula, para textos: "dólares".
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

# Todos los países del mundo: código ISO 3166-1 alpha-2 y su nombre en español.
# La bandera se calcula sola a partir del código (bandera_de) y el nombre se
# traduce en el navegador al idioma elegido (Intl.DisplayNames). El dinero es el
# mismo en todas partes (dólares), así que el país solo decide la bandera.
_CODIGOS_PAISES: tuple[tuple[str, str], ...] = (
    ("AF", "Afganistán"),
    ("AL", "Albania"),
    ("DE", "Alemania"),
    ("AD", "Andorra"),
    ("AO", "Angola"),
    ("AI", "Anguila"),
    ("AG", "Antigua y Barbuda"),
    ("AQ", "Antártida"),
    ("SA", "Arabia Saudí"),
    ("DZ", "Argelia"),
    ("AR", "Argentina"),
    ("AM", "Armenia"),
    ("AW", "Aruba"),
    ("AU", "Australia"),
    ("AT", "Austria"),
    ("AZ", "Azerbaiyán"),
    ("BS", "Bahamas"),
    ("BD", "Bangladés"),
    ("BB", "Barbados"),
    ("BH", "Baréin"),
    ("BZ", "Belice"),
    ("BJ", "Benín"),
    ("BM", "Bermudas"),
    ("BY", "Bielorrusia"),
    ("BO", "Bolivia"),
    ("BA", "Bosnia y Herzegovina"),
    ("BW", "Botsuana"),
    ("BR", "Brasil"),
    ("BN", "Brunéi"),
    ("BG", "Bulgaria"),
    ("BF", "Burkina Faso"),
    ("BI", "Burundi"),
    ("BT", "Bután"),
    ("BE", "Bélgica"),
    ("CV", "Cabo Verde"),
    ("KH", "Camboya"),
    ("CM", "Camerún"),
    ("CA", "Canadá"),
    ("BQ", "Caribe neerlandés"),
    ("QA", "Catar"),
    ("TD", "Chad"),
    ("CZ", "Chequia"),
    ("CL", "Chile"),
    ("CN", "China"),
    ("CY", "Chipre"),
    ("VA", "Ciudad del Vaticano"),
    ("CO", "Colombia"),
    ("KM", "Comoras"),
    ("CG", "Congo"),
    ("KP", "Corea del Norte"),
    ("KR", "Corea del Sur"),
    ("CR", "Costa Rica"),
    ("HR", "Croacia"),
    ("CU", "Cuba"),
    ("CW", "Curazao"),
    ("CI", "Côte d’Ivoire"),
    ("DK", "Dinamarca"),
    ("DM", "Dominica"),
    ("EC", "Ecuador"),
    ("EG", "Egipto"),
    ("SV", "El Salvador"),
    ("AE", "Emiratos Árabes Unidos"),
    ("ER", "Eritrea"),
    ("SK", "Eslovaquia"),
    ("SI", "Eslovenia"),
    ("ES", "España"),
    ("US", "Estados Unidos"),
    ("EE", "Estonia"),
    ("SZ", "Esuatini"),
    ("ET", "Etiopía"),
    ("PH", "Filipinas"),
    ("FI", "Finlandia"),
    ("FJ", "Fiyi"),
    ("FR", "Francia"),
    ("GA", "Gabón"),
    ("GM", "Gambia"),
    ("GE", "Georgia"),
    ("GH", "Ghana"),
    ("GI", "Gibraltar"),
    ("GD", "Granada"),
    ("GR", "Grecia"),
    ("GL", "Groenlandia"),
    ("GP", "Guadalupe"),
    ("GU", "Guam"),
    ("GT", "Guatemala"),
    ("GF", "Guayana Francesa"),
    ("GG", "Guernesey"),
    ("GN", "Guinea"),
    ("GQ", "Guinea Ecuatorial"),
    ("GW", "Guinea-Bisáu"),
    ("GY", "Guyana"),
    ("HT", "Haití"),
    ("HN", "Honduras"),
    ("HU", "Hungría"),
    ("IN", "India"),
    ("ID", "Indonesia"),
    ("IQ", "Irak"),
    ("IE", "Irlanda"),
    ("IR", "Irán"),
    ("BV", "Isla Bouvet"),
    ("NF", "Isla Norfolk"),
    ("IM", "Isla de Man"),
    ("CX", "Isla de Navidad"),
    ("IS", "Islandia"),
    ("AX", "Islas Aland"),
    ("KY", "Islas Caimán"),
    ("CC", "Islas Cocos"),
    ("CK", "Islas Cook"),
    ("FO", "Islas Feroe"),
    ("GS", "Islas Georgia del Sur y Sandwich del Sur"),
    ("HM", "Islas Heard y McDonald"),
    ("FK", "Islas Malvinas"),
    ("MP", "Islas Marianas del Norte"),
    ("MH", "Islas Marshall"),
    ("PN", "Islas Pitcairn"),
    ("SB", "Islas Salomón"),
    ("TC", "Islas Turcas y Caicos"),
    ("VG", "Islas Vírgenes Británicas"),
    ("VI", "Islas Vírgenes de EE. UU."),
    ("UM", "Islas menores alejadas de EE. UU."),
    ("IL", "Israel"),
    ("IT", "Italia"),
    ("JM", "Jamaica"),
    ("JP", "Japón"),
    ("JE", "Jersey"),
    ("JO", "Jordania"),
    ("KZ", "Kazajistán"),
    ("KE", "Kenia"),
    ("KG", "Kirguistán"),
    ("KI", "Kiribati"),
    ("KW", "Kuwait"),
    ("LA", "Laos"),
    ("LS", "Lesoto"),
    ("LV", "Letonia"),
    ("LR", "Liberia"),
    ("LY", "Libia"),
    ("LI", "Liechtenstein"),
    ("LT", "Lituania"),
    ("LU", "Luxemburgo"),
    ("LB", "Líbano"),
    ("MK", "Macedonia del Norte"),
    ("MG", "Madagascar"),
    ("MY", "Malasia"),
    ("MW", "Malaui"),
    ("MV", "Maldivas"),
    ("ML", "Mali"),
    ("MT", "Malta"),
    ("MA", "Marruecos"),
    ("MQ", "Martinica"),
    ("MU", "Mauricio"),
    ("MR", "Mauritania"),
    ("YT", "Mayotte"),
    ("FM", "Micronesia"),
    ("MD", "Moldavia"),
    ("MN", "Mongolia"),
    ("ME", "Montenegro"),
    ("MS", "Montserrat"),
    ("MZ", "Mozambique"),
    ("MM", "Myanmar (Birmania)"),
    ("MX", "México"),
    ("MC", "Mónaco"),
    ("NA", "Namibia"),
    ("NR", "Nauru"),
    ("NP", "Nepal"),
    ("NI", "Nicaragua"),
    ("NG", "Nigeria"),
    ("NU", "Niue"),
    ("NO", "Noruega"),
    ("NC", "Nueva Caledonia"),
    ("NZ", "Nueva Zelanda"),
    ("NE", "Níger"),
    ("OM", "Omán"),
    ("PK", "Pakistán"),
    ("PW", "Palaos"),
    ("PA", "Panamá"),
    ("PG", "Papúa Nueva Guinea"),
    ("PY", "Paraguay"),
    ("NL", "Países Bajos"),
    ("PE", "Perú"),
    ("PF", "Polinesia Francesa"),
    ("PL", "Polonia"),
    ("PT", "Portugal"),
    ("PR", "Puerto Rico"),
    ("HK", "RAE de Hong Kong (China)"),
    ("MO", "RAE de Macao (China)"),
    ("GB", "Reino Unido"),
    ("CF", "República Centroafricana"),
    ("CD", "República Democrática del Congo"),
    ("DO", "República Dominicana"),
    ("RE", "Reunión"),
    ("RW", "Ruanda"),
    ("RO", "Rumanía"),
    ("RU", "Rusia"),
    ("WS", "Samoa"),
    ("AS", "Samoa Americana"),
    ("BL", "San Bartolomé"),
    ("KN", "San Cristóbal y Nieves"),
    ("SM", "San Marino"),
    ("MF", "San Martín"),
    ("PM", "San Pedro y Miquelón"),
    ("VC", "San Vicente y las Granadinas"),
    ("SH", "Santa Elena"),
    ("LC", "Santa Lucía"),
    ("ST", "Santo Tomé y Príncipe"),
    ("SN", "Senegal"),
    ("RS", "Serbia"),
    ("SC", "Seychelles"),
    ("SL", "Sierra Leona"),
    ("SG", "Singapur"),
    ("SX", "Sint Maarten"),
    ("SY", "Siria"),
    ("SO", "Somalia"),
    ("LK", "Sri Lanka"),
    ("ZA", "Sudáfrica"),
    ("SD", "Sudán"),
    ("SS", "Sudán del Sur"),
    ("SE", "Suecia"),
    ("CH", "Suiza"),
    ("SR", "Surinam"),
    ("SJ", "Svalbard y Jan Mayen"),
    ("EH", "Sáhara Occidental"),
    ("TH", "Tailandia"),
    ("TW", "Taiwán"),
    ("TZ", "Tanzania"),
    ("TJ", "Tayikistán"),
    ("IO", "Territorio Británico del Océano Índico"),
    ("TF", "Territorios Australes Franceses"),
    ("PS", "Territorios Palestinos"),
    ("TL", "Timor-Leste"),
    ("TG", "Togo"),
    ("TK", "Tokelau"),
    ("TO", "Tonga"),
    ("TT", "Trinidad y Tobago"),
    ("TM", "Turkmenistán"),
    ("TR", "Turquía"),
    ("TV", "Tuvalu"),
    ("TN", "Túnez"),
    ("UA", "Ucrania"),
    ("UG", "Uganda"),
    ("UY", "Uruguay"),
    ("UZ", "Uzbekistán"),
    ("VU", "Vanuatu"),
    ("VE", "Venezuela"),
    ("VN", "Vietnam"),
    ("WF", "Wallis y Futuna"),
    ("YE", "Yemen"),
    ("DJ", "Yibuti"),
    ("ZM", "Zambia"),
    ("ZW", "Zimbabue"),
)


def bandera_de(code: str) -> str:
    """La bandera de un país a partir de su código ISO ('VE' -> 🇻🇪)."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


# El dinero es el mismo en todo el mundo: dólares, con el símbolo 🫰.
# Se genera la lista entera para que cualquier país del mundo pueda jugar.
PAISES: tuple[Pais, ...] = tuple(
    Pais(code, nombre, "USD", "🫰", bandera_de(code), "", "dólares")
    for code, nombre in _CODIGOS_PAISES
)

# Código de país que devuelve el detector de IP -> nuestro código (ahora todos).
IP_COUNTRY_MAP: dict[str, str] = {p.code: p.code for p in PAISES}


def _env(clave: str, por_defecto: str) -> str:
    return os.environ.get(clave) or por_defecto


# ---------------------------------------------------------------------------
# Métodos de pago
# ---------------------------------------------------------------------------

def _cuenta_paypal() -> tuple[DatoCuenta, ...]:
    """La cuenta PayPal de la casa: donde se recibe el dinero y se paga."""
    return (DatoCuenta("PayPal", _env("BINGO_PAGO_PAYPAL", "taktak.messenger@gmail.com"),
                       "Envía el dinero a este correo de PayPal (amigos y familiares)"),)


def _cuenta_cripto() -> tuple[DatoCuenta, ...]:
    """La billetera USDT de la casa. La dirección se puede cambiar en Render."""
    return (
        DatoCuenta("Moneda", "USDT (Tether)", "Manda la cantidad exacta en USDT"),
        DatoCuenta("Red", _env("BINGO_PAGO_CRIPTO_RED", "ERC-20 (Ethereum)"),
                   "Usa SOLO esta red, o el dinero se pierde"),
        DatoCuenta("Billetera",
                   _env("BINGO_PAGO_CRIPTO_DIRECCION",
                        "0xbffd97a8e2ea154ca42aeea0fbb7990fa153ca48"),
                   "Copia la dirección y manda el USDT aquí"),
    )


METODOS_PAGO: tuple[MetodoPago, ...] = (
    MetodoPago(
        id="paypal", nombre="PayPal", country="*", moneda="USD",
        fields=(
            CampoPago("correo", "Correo de PayPal", "tu@correo.com", True, "email"),
            CampoPago("titular", "Nombre del titular", "Nombre y apellido", True, "text"),
        ),
        _cuentas=_cuenta_paypal,
    ),
    MetodoPago(
        id="cripto", nombre="USDT (cripto)", country="*", moneda="USD",
        fields=(
            CampoPago("red", "Red", "TRC-20 (Tron)", True, "text"),
            CampoPago("direccion", "Dirección de la billetera", "T...", True, "text"),
        ),
        _cuentas=_cuenta_cripto,
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
    return METODOS_PAGO[0]


def metodos_de_pais(code: str | None) -> list[MetodoPago]:
    """Los métodos de cobro. Son los mismos en todos los países: PayPal y USDT."""
    if not code:
        return []
    return list(METODOS_PAGO)


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
# céntimos de dólar, que es la única moneda. La conversión quedó en 1 (no hay
# nada que convertir), pero se conservan las funciones por compatibilidad.


def tasa_de(code: str | None) -> Decimal:
    """La tasa de conversión. Siempre 1: todo el dinero está en dólares.

    Se mantiene la función para no tocar a quien la llama, pero ya no lee nada
    del entorno. Así, aunque quede una variable BINGO_TASA_XX vieja puesta en
    Render, no puede mover ni un céntimo.
    """
    return Decimal("1")


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
# La ganancia de la app cae en una sola cuenta para todo el mundo: el PayPal de
# la casa y su billetera USDT. Se configuran por variables de entorno, para poder
# cambiarlas en Render sin tocar el código.


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


# La cuenta de administración es la misma para todos: PayPal y la billetera
# USDT donde cae el dinero de la casa.


def _lineas_admin() -> tuple[LineaCuenta, ...]:
    """El PayPal y la billetera USDT de la casa. Son los mismos en todo el mundo,
    así que se leen de dos variables compartidas (no una por país)."""
    return (
        LineaCuenta("PayPal", _env("BINGO_ADMIN_PAYPAL",
                                   _env("BINGO_PAGO_PAYPAL", "taktak.messenger@gmail.com"))),
        LineaCuenta("Billetera USDT",
                    _env("BINGO_ADMIN_CRIPTO",
                         _env("BINGO_PAGO_CRIPTO_DIRECCION",
                              "0xbffd97a8e2ea154ca42aeea0fbb7990fa153ca48"))),
    )


def cuenta_admin(code: str) -> CuentaAdmin:
    """La cuenta donde se cobra la ganancia de la app. Es la misma en todo el mundo."""
    code = (code or PAIS_POR_DEFECTO).strip().upper()
    if not es_pais_valido(code):
        code = PAIS_POR_DEFECTO
    return CuentaAdmin(
        pais=code,
        banco="PayPal / USDT",
        titular=_env("BINGO_ADMIN_TITULAR", "BingoPiramide777"),
        moneda=moneda_de(code),
        lineas=_lineas_admin(),
    )


def cuentas_admin() -> list[CuentaAdmin]:
    """La cuenta de la casa. Es una sola para todo el mundo: PayPal y USDT."""
    return [cuenta_admin(PAIS_POR_DEFECTO)]
