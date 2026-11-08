"""Servicio de fichas de cobro: junta el almacén, el cifrado y la validación.

El almacén guarda un texto cifrado y no sabe qué hay dentro. Aquí se descifra
para quien tenga permiso (el propio jugador o la administración) y se vuelve a
cifrar al guardar.

La clave se resuelve así:
1. ``BINGO_DATOS_CLAVE`` en el entorno, si está puesta (lo recomendado).
2. Si no, una clave guardada en la tabla ``meta``, generada la primera vez.

Si no hay clave por ningún lado, la primera vez se genera y se guarda. Así la
app funciona recién instalada sin configurar nada, y la clave sobrevive a los
reinicios porque vive en la misma base de datos.
"""

from __future__ import annotations

from .almacen import Almacen
from .datos_cobro import ErrorDeDatosCobro, FichaCobro, deserializar, serializar, validar
from .secretos import CLAVE_EN_META, ErrorDeCifrado, cifrar, clave_desde_entorno, clave_nueva, descifrar


class ErrorDeFicha(ValueError):
    """No se pudo guardar o leer la ficha de cobro."""


class FichasCobro:
    def __init__(self, almacen: Almacen, clave: bytes | None = None) -> None:
        self.almacen = almacen
        self._clave = clave
        self._de_entorno = clave is None

    @property
    def clave(self) -> bytes:
        """La clave de cifrado, resolviéndola la primera vez que hace falta."""
        if self._clave is None:
            self._clave = self._resolver_clave()
        return self._clave

    def _resolver_clave(self) -> bytes:
        if self._de_entorno:
            del_entorno = clave_desde_entorno()
            if del_entorno is not None:
                return del_entorno
        guardada = self.almacen.meta(CLAVE_EN_META)
        if guardada:
            from .secretos import clave_desde_texto

            return clave_desde_texto(guardada)
        # Primera vez y sin variable de entorno: se genera y se guarda.
        nueva = clave_nueva()
        self.almacen.guardar_meta(CLAVE_EN_META, nueva)
        return bytes.fromhex(nueva)

    def guardar(self, correo: str, metodo: str, campos: dict) -> FichaCobro:
        correo = (correo or "").strip().lower()
        if not correo:
            raise ErrorDeDatosCobro("Hace falta un correo.")
        if self.almacen.usuario(correo) is None:
            raise ErrorDeDatosCobro(f"No existe la cuenta {correo}.")
        limpios = validar(metodo, campos)
        paquete = cifrar(serializar(metodo, limpios), self.clave)
        self.almacen.guardar_datos_cobro(correo, paquete)
        return FichaCobro(correo=correo, metodo=metodo, campos=limpios)

    def de(self, correo: str) -> FichaCobro:
        """Devuelve la ficha de un jugador (vacía si no tiene)."""
        correo = (correo or "").strip().lower()
        fila = self.almacen.usuario(correo)
        if fila is None:
            return FichaCobro(correo=correo, metodo="", campos={})
        paquete = ""
        claves = fila.keys()
        if "datos_cobro" in claves:
            paquete = fila["datos_cobro"] or ""
        if not paquete:
            return FichaCobro(correo=correo, metodo="", campos={})
        try:
            texto = descifrar(paquete, self.clave)
        except ErrorDeCifrado as exc:
            # La clave cambió o alguien tocó la fila. No se inventa una ficha:
            # se avisa, y el jugador la vuelve a poner.
            raise ErrorDeFicha(
                f"No se pudieron leer los datos de cobro de {correo}: {exc}") from None
        metodo, campos = deserializar(texto)
        return FichaCobro(correo=correo, metodo=metodo, campos=campos)

    def de_seguro(self, correo: str) -> FichaCobro:
        """Como ``de``, pero devuelve una ficha vacía si no se puede leer.

        Para listados: una ficha ilegible no debe tumbar toda la lista.
        """
        try:
            return self.de(correo)
        except ErrorDeFicha:
            return FichaCobro(correo=(correo or "").strip().lower(), metodo="", campos={})

    def borrar(self, correo: str) -> None:
        correo = (correo or "").strip().lower()
        self.almacen.guardar_datos_cobro(correo, "")
