"""Pruebas de la vinculación de billeteras a una cuenta."""

from __future__ import annotations

import time
import unittest

from nucleo.almacen import Almacen
from nucleo.billeteras import Billeteras, ErrorDeBilleteraVinculada, mensaje_de_desafio
from nucleo.firmas import ErrorDeBilletera
from nucleo.usuarios import Usuarios

CORREO = "ana@correo.com"
NONCE = "0123456789abcdef0123456789abcdef"

EVM_DIRECCION = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"
EVM_FIRMA = ("9a1056e8e82574982c69abda8d3ed5234dd3b193a566e51fd103b301e0e3709d"
             "4b2aa9c58bd1f6255f3e620fa31aec9723ec41c58283884f99002ab4a213a5641b")

SOL_DIRECCION = "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF"
SOL_FIRMA = ("5f956cc7c32db006a0cf7f0028dfacb36b1cb609dde7d59dc4f98fb8f4a28445"
             "1fbf4777a4fdbc2adcfbf8406b99017d9ffacb45832a017b7f3f06ef3d1e930e")


class BilleteraTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.usuarios.registrar(CORREO, "miClaveSegura1")
        self.billeteras = Billeteras(self.almacen)

    def tearDown(self):
        self.almacen.cerrar()

    def _desafio_con_nonce(self, nonce=NONCE):
        """Deja el desafío con un nonce fijo, para usar las firmas de prueba."""
        import json
        self.almacen.guardar_meta("billetera_desafio:" + CORREO,
                                  json.dumps({"nonce": nonce,
                                              "caduca": time.time() + 300}))
        return mensaje_de_desafio(CORREO, nonce)

    def test_vincular_evm(self):
        self._desafio_con_nonce()
        b = self.billeteras.vincular(CORREO, EVM_DIRECCION, EVM_FIRMA, "evm")
        self.assertEqual(b["red"], "evm")
        self.assertEqual(b["direccion"], EVM_DIRECCION)
        guardada = self.billeteras.de(CORREO)
        self.assertTrue(guardada["configurada"])
        self.assertEqual(guardada["direccion"], EVM_DIRECCION)

    def test_vincular_solana(self):
        self._desafio_con_nonce()
        b = self.billeteras.vincular(CORREO, SOL_DIRECCION, SOL_FIRMA, "")
        self.assertEqual(b["red"], "solana")

    def test_firma_de_otra_direccion_no_vale(self):
        self._desafio_con_nonce()
        with self.assertRaises(ErrorDeBilleteraVinculada):
            self.billeteras.vincular(CORREO, "0x" + "ab" * 20, EVM_FIRMA, "evm")

    def test_firma_manoseada_no_vale(self):
        self._desafio_con_nonce()
        # Se toca un byte de "r" (no el último, que es la "v" y no cambia la firma).
        firma = bytearray(bytes.fromhex(EVM_FIRMA))
        firma[2] ^= 1
        with self.assertRaises(ErrorDeBilleteraVinculada):
            self.billeteras.vincular(CORREO, EVM_DIRECCION, firma.hex(), "evm")

    def test_sin_desafio_no_se_puede(self):
        with self.assertRaises(ErrorDeBilleteraVinculada):
            self.billeteras.vincular(CORREO, EVM_DIRECCION, EVM_FIRMA, "evm")

    def test_desafio_caducado(self):
        import json
        self.almacen.guardar_meta("billetera_desafio:" + CORREO,
                                  json.dumps({"nonce": NONCE, "caduca": time.time() - 1}))
        with self.assertRaises(ErrorDeBilleteraVinculada):
            self.billeteras.vincular(CORREO, EVM_DIRECCION, EVM_FIRMA, "evm")

    def test_la_firma_solo_vale_una_vez(self):
        self._desafio_con_nonce()
        self.billeteras.vincular(CORREO, EVM_DIRECCION, EVM_FIRMA, "evm")
        with self.assertRaises(ErrorDeBilleteraVinculada):
            self.billeteras.vincular(CORREO, EVM_DIRECCION, EVM_FIRMA, "evm")

    def test_desafio_lleva_el_correo_y_el_nonce(self):
        reto = self.billeteras.desafio(CORREO)
        self.assertIn(CORREO, reto["mensaje"])
        self.assertIn(reto["nonce"], reto["mensaje"])

    def test_desafio_caduca_en_el_futuro(self):
        reto = self.billeteras.desafio(CORREO)
        self.assertGreater(reto["caduca"], time.time())

    def test_cuenta_inexistente(self):
        self._desafio_con_nonce()
        with self.assertRaises(ErrorDeBilleteraVinculada):
            self.billeteras.vincular("otro@correo.com", EVM_DIRECCION, EVM_FIRMA, "evm")

    def test_direccion_invalida(self):
        self._desafio_con_nonce()
        with self.assertRaises((ErrorDeBilleteraVinculada, ErrorDeBilletera)):
            self.billeteras.vincular(CORREO, "no-es-una-direccion", EVM_FIRMA, "")

    def test_borrar(self):
        self._desafio_con_nonce()
        self.billeteras.vincular(CORREO, EVM_DIRECCION, EVM_FIRMA, "evm")
        self.billeteras.borrar(CORREO)
        self.assertIsNone(self.billeteras.de(CORREO))

    def test_sin_billetera_no_hay_nada(self):
        self.assertIsNone(self.billeteras.de(CORREO))


if __name__ == "__main__":
    unittest.main()
