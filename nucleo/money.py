"""Dinero exacto. Nada de float: un céntimo perdido es un cliente enfadado.

Todo importe se guarda en céntimos (enteros). Se convierte a texto solo para
mostrarlo. Así 0.1 + 0.2 son exactamente 0.3, no 0.30000000000000004.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTIMOS = Decimal("0.01")


class ErrorDeDinero(ValueError):
    """Importe mal formado o fuera de rango."""


def a_centimos(importe: object) -> int:
    """Convierte un importe (texto, número o Decimal) a céntimos enteros.

    Acepta "10.50", "10,50" y 10.5. Rechaza negativos, NaN, infinito y más de
    dos decimales reales.
    """
    if isinstance(importe, bool):
        raise ErrorDeDinero("Un booleano no es un importe.")
    if isinstance(importe, int):
        return importe * 100
    if isinstance(importe, float):
        # Un float ya viene con su error de redondeo; pasarlo por texto lo fija.
        importe = repr(importe)
    texto = str(importe).strip().replace(",", ".")
    if not texto:
        raise ErrorDeDinero("Importe vacío.")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise ErrorDeDinero(f"Importe no válido: {importe!r}.") from None
    if not valor.is_finite():
        raise ErrorDeDinero("Importe no finito.")
    if valor < 0:
        raise ErrorDeDinero("El importe no puede ser negativo.")
    # Dos decimales como máximo; el resto se redondea al alza (a favor del cliente
    # no: se redondea al céntimo más próximo, y así no se pierde ni se inventa).
    centimos = int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return centimos


def a_texto(centimos: int, moneda: str | None = None) -> str:
    """Formatea céntimos como texto, con el símbolo de la moneda de quien mira.

    El dinero está siempre en dólares. Si no se pasa moneda, se usa el símbolo del
    país de la petición (que hoy es "$" en todos). Si se pasa ``moneda`` explícita,
    se usa ese símbolo tal cual (lo usa ``paises.formatear_local``).
    """
    if not isinstance(centimos, int):
        raise ErrorDeDinero("Los céntimos deben ser enteros.")
    if moneda is None:
        from .paises import de_base, pais_actual, simbolo_de

        code = pais_actual()
        centimos = de_base(centimos, code)
        moneda = simbolo_de(code)
    negativo = centimos < 0
    entero, resto = divmod(abs(centimos), 100)
    miles = f"{entero:,}".replace(",", ".")
    signo = "-" if negativo else ""
    return f"{signo}{moneda} {miles},{resto:02d}"


def multiplicar(centimos: int, factor: Decimal | int | str) -> int:
    """Multiplica un importe por un factor (ej. el premio de 30x) sin perder céntimos."""
    if not isinstance(centimos, int):
        raise ErrorDeDinero("Los céntimos deben ser enteros.")
    f = Decimal(str(factor))
    if not f.is_finite() or f < 0:
        raise ErrorDeDinero(f"Factor no válido: {factor!r}.")
    return int((Decimal(centimos) * f).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
