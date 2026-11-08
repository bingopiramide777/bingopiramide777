"""Ficha de cobro de cada jugador: dónde quiere que le paguen.

El problema que resuelve: hoy, para pagarle un premio o un retiro a alguien, la
administración tiene que pedirle los datos por chat cada vez. Y Glenis IA, que
prepara los pagos, no tiene de dónde sacarlos.

Con la ficha, el jugador los deja puestos una vez y ya están ahí. Se guardan
**cifrados** (ver ``nucleo.secretos``): quien abra la base de datos no ve un
número de cuenta, ve un paquete cifrado.

Métodos soportados: los mismos que la app ya usa para cobrar, sin pasarelas de
terceros. Pago Móvil (VE), Nequi (CO), MACH (CL), Cash App (US) y transferencia
bancaria. Nada de PayPal.

Qué NO hace este módulo: mover dinero. Guarda y devuelve los datos de cobro. El
pago real lo confirma una persona; Glenis solo lo prepara.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import secretos

# Métodos de cobro. Coinciden con los de depósito (nucleo.depositos.METODOS)
# más la transferencia bancaria clásica.
METODOS = ("pago_movil", "nequi", "mach", "cashapp", "transferencia")

# Qué campos pide cada método. El orden es el que se muestra en el formulario.
CAMPOS: dict[str, tuple[tuple[str, str], ...]] = {
    "pago_movil": (("titular", "Titular"), ("banco", "Banco"),
                   ("telefono", "Teléfono"), ("cedula", "Cédula / RIF")),
    "nequi": (("titular", "Titular"), ("telefono", "Número Nequi")),
    "mach": (("titular", "Titular"), ("telefono", "Número MACH"), ("rut", "RUT (opcional)")),
    "cashapp": (("titular", "Titular"), ("cashtag", "Cashtag o teléfono")),
    "transferencia": (("titular", "Titular"), ("banco", "Banco"),
                      ("cuenta", "Número de cuenta"), ("tipo_cuenta", "Tipo de cuenta")),
}

# Un teléfono/cuenta: dígitos con guiones, puntos y un + inicial.
_DIGITOS = re.compile(r"^[+]?[\d\s.\-()]{5,30}$")
# La cédula/RIF lleva una letra delante en varios países (V-12345678, J-400...).
_DOCUMENTO = re.compile(r"^[A-Za-z]{0,2}[\-.\s]?[\d.\-\s]{5,30}$")
_LARGO_MAXIMO = 120


class ErrorDeDatosCobro(ValueError):
    """Los datos de cobro no son válidos."""


@dataclass
class FichaCobro:
    correo: str
    metodo: str
    campos: dict[str, str] = field(default_factory=dict)

    @property
    def configurada(self) -> bool:
        return bool(self.metodo) and bool(self.campos)

    def a_dict(self) -> dict:
        """Vista para el frontend y para Glenis: método, etiquetas y valores."""
        campos = []
        for clave, etiqueta in CAMPOS.get(self.metodo, ()):
            valor = self.campos.get(clave, "")
            if valor:
                campos.append({"key": clave, "label": etiqueta, "value": valor})
        return {"correo": self.correo, "metodo": self.metodo, "campos": campos,
                "configurada": self.configurada}


def _limpiar(valor: object) -> str:
    return str(valor or "").strip()[:_LARGO_MAXIMO]


def validar(metodo: str, campos: dict) -> dict[str, str]:
    """Comprueba el método y los campos. Devuelve solo los campos que aplican.

    No se inventa nada: si un campo obligatorio falta, se avisa. El campo
    "rut" de MACH es el único opcional, y así se declara en CAMPOS.
    """
    metodo = (metodo or "").strip().lower()
    if metodo not in METODOS:
        raise ErrorDeDatosCobro(
            f"Método de cobro no válido. Los permitidos son: {', '.join(METODOS)}.")
    campos = campos if isinstance(campos, dict) else {}
    limpios: dict[str, str] = {}
    for clave, etiqueta in CAMPOS[metodo]:
        valor = _limpiar(campos.get(clave, ""))
        opcional = "opcional" in etiqueta.lower()
        if not valor:
            if opcional:
                continue
            raise ErrorDeDatosCobro(f"Falta el dato de cobro: {etiqueta}.")
        if clave in ("cedula", "rut") and not _DOCUMENTO.match(valor):
            raise ErrorDeDatosCobro(f"El dato «{etiqueta}» no tiene buena pinta.")
        if clave in ("telefono", "cuenta") and not _DIGITOS.match(valor):
            raise ErrorDeDatosCobro(f"El dato «{etiqueta}» no tiene buena pinta.")
        limpios[clave] = valor
    return limpios


def serializar(metodo: str, campos: dict[str, str]) -> str:
    """Convierte la ficha a texto para cifrar y guardar."""
    return json.dumps({"metodo": metodo, "campos": campos}, ensure_ascii=False, sort_keys=True)


def deserializar(texto: str) -> tuple[str, dict[str, str]]:
    """Recupera (método, campos) del texto guardado."""
    if not texto:
        return "", {}
    try:
        datos = json.loads(texto)
    except ValueError:
        return "", {}
    if not isinstance(datos, dict):
        return "", {}
    metodo = datos.get("metodo", "")
    campos = datos.get("campos", {})
    if not isinstance(campos, dict):
        campos = {}
    return str(metodo), {str(k): str(v) for k, v in campos.items()}


def resumen_publico(ficha: FichaCobro) -> str:
    """Un resumen corto y sin datos sensibles, para mostrar en listas.

    Se enseña solo el método y lo justo para reconocerlo (por ejemplo, los
    últimos dígitos del teléfono). El dato completo solo lo ve quien cobra.
    """
    if not ficha.configurada:
        return ""
    partes = []
    for clave, etiqueta in CAMPOS.get(ficha.metodo, ()):
        valor = ficha.campos.get(clave, "")
        if not valor:
            continue
        if clave in ("telefono", "cuenta", "cashtag"):
            visible = valor[-4:] if len(valor) > 4 else valor
            partes.append(f"{etiqueta} ···{visible}")
        elif clave == "titular":
            partes.append(valor)
    return " · ".join(partes)
