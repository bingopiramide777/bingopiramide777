"""Idiomas de la interfaz.

La app se juega en varios países y por gente de cualquier origen: un jugador
chino en Estados Unidos tiene que poder leer la mesa en chino. El idioma es
independiente del país: el país decide la moneda y el método de cobro; el idioma
decide los textos.

Igual que el país, el idioma activo vive en una variable de contexto por petición
para que el servidor y el frontend no tengan que pasarlo por cada llamada.

Los textos traducidos viven en el frontend (``web/static/i18n.js``); aquí solo se
declara el catálogo, la detección por cabecera y el idioma activo.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass

IDIOMA_POR_DEFECTO = "es"


@dataclass(frozen=True)
class Idioma:
    code: str
    nombre: str      # Nombre del idioma en su propio idioma (para el selector).
    locale: str      # Etiqueta BCP-47 para formatear fechas y números.
    bandera: str

    def a_dict(self) -> dict:
        return {"code": self.code, "name": self.nombre, "locale": self.locale,
                "flag": self.bandera}


IDIOMAS: tuple[Idioma, ...] = (
    Idioma("es", "Español", "es-VE", "🇪🇸"),
    Idioma("en", "English", "en-US", "🇺🇸"),
    Idioma("zh", "中文", "zh-CN", "🇨🇳"),
)

# Primeras letras de la cabecera Accept-Language -> nuestro código. Se mira el
# idioma base ("zh-CN" -> "zh") porque los navegadores mandan variantes.
PREFIJOS: dict[str, str] = {
    "es": "es", "en": "en", "zh": "zh",
}


def idioma(code: str | None) -> Idioma | None:
    if not code:
        return None
    code = str(code).strip().lower().replace("_", "-")
    base = code.split("-")[0]
    return next((i for i in IDIOMAS if i.code == base), None)


def es_idioma_valido(code: str | None) -> bool:
    return idioma(code) is not None


def locale_de(code: str | None) -> str:
    i = idioma(code) or idioma(IDIOMA_POR_DEFECTO)
    return i.locale


def detectar(accept_language: str | None) -> str:
    """Elige el mejor idioma para una cabecera Accept-Language.

    Se respeta el orden de preferencia del navegador y se cae al idioma por
    defecto cuando no se reconoce ninguno.
    """
    if not accept_language:
        return IDIOMA_POR_DEFECTO
    for trozo in accept_language.split(","):
        etiqueta = trozo.split(";")[0].strip().lower()
        base = etiqueta.split("-")[0]
        if base in PREFIJOS:
            return PREFIJOS[base]
    return IDIOMA_POR_DEFECTO


def catalogo() -> dict:
    return {
        "idiomas": [i.a_dict() for i in IDIOMAS],
        "idioma_por_defecto": IDIOMA_POR_DEFECTO,
        "idioma_actual": idioma_actual(),
    }


# ---------------------------------------------------------------------------
# Idioma activo de la petición
# ---------------------------------------------------------------------------

_idioma_actual: contextvars.ContextVar[str] = contextvars.ContextVar(
    "idioma_actual", default=IDIOMA_POR_DEFECTO)


def idioma_actual() -> str:
    return _idioma_actual.get()


def usar_idioma(code: str | None) -> str:
    elegido = code if es_idioma_valido(code) else IDIOMA_POR_DEFECTO
    _idioma_actual.set(elegido)
    return elegido
