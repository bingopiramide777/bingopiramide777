"""Pruebas del cifrado de datos sensibles (nucleo/secretos.py).

Lo que se comprueba, y por qué:
- Que cifrar y descifrar devuelva lo mismo (ida y vuelta).
- Que el mismo texto no dé el mismo cifrado dos veces (nonce nuevo).
- Que tocar el cifrado o cambiar la clave falle en vez de devolver basura.
- Que una clave de entorno en texto libre también sirva (se deriva).
"""

import unittest

from nucleo import secretos


class TestCifrado(unittest.TestCase):
    def setUp(self):
        self.clave = bytes(range(32))

    def test_ida_y_vuelta(self):
        for texto in ("", "0416-7677264", "Banco de Venezuela · 12.256.618",
                      "你好，世界", "emoji 🔐 y acentos: ñáéíóú"):
            with self.subTest(texto=texto):
                paquete = secretos.cifrar(texto, self.clave)
                self.assertEqual(secretos.descifrar(paquete, self.clave), texto)

    def test_el_mismo_texto_no_da_el_mismo_cifrado(self):
        # Dos cifrados del mismo texto tienen que ser distintos: si no, se podría
        # ver desde fuera que dos jugadores tienen el mismo número de cuenta.
        a = secretos.cifrar("0416-7677264", self.clave)
        b = secretos.cifrar("0416-7677264", self.clave)
        self.assertNotEqual(a, b)
        self.assertEqual(secretos.descifrar(a, self.clave), secretos.descifrar(b, self.clave))

    def test_datos_alterados_fallan(self):
        paquete = secretos.cifrar("cuenta secreta", self.clave)
        crudo = bytearray(secretos.base64.b64decode(paquete))
        crudo[-1] ^= 0x01  # se cambia un bit de la etiqueta
        roto = secretos.base64.b64encode(bytes(crudo)).decode("ascii")
        with self.assertRaises(secretos.ErrorDeCifrado):
            secretos.descifrar(roto, self.clave)

    def test_otra_clave_falla(self):
        paquete = secretos.cifrar("cuenta secreta", self.clave)
        with self.assertRaises(secretos.ErrorDeCifrado):
            secretos.descifrar(paquete, bytes([9] * 32))

    def test_texto_cifrado_incompleto(self):
        with self.assertRaises(secretos.ErrorDeCifrado):
            secretos.descifrar("corto", self.clave)

    def test_clave_de_largo_equivocado(self):
        with self.assertRaises(secretos.ErrorDeCifrado):
            secretos.cifrar("hola", b"clave corta")

    def test_clave_desde_texto_hex(self):
        hexa = secretos.clave_nueva()
        self.assertEqual(len(hexa), 64)
        self.assertEqual(secretos.clave_desde_texto(hexa), bytes.fromhex(hexa))

    def test_clave_desde_texto_libre_se_deriva(self):
        # Una frase puesta a mano en Render también sirve: se deriva a 32 bytes.
        clave = secretos.clave_desde_texto("mi frase secreta")
        self.assertEqual(len(clave), 32)
        self.assertEqual(clave, secretos.clave_desde_texto("mi frase secreta"))
        self.assertNotEqual(clave, secretos.clave_desde_texto("otra frase"))


if __name__ == "__main__":
    unittest.main()
