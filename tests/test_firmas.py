"""Pruebas de la verificación de firmas de billeteras.

Los vectores están fijos (generados con eth-account y PyNaCl) para que la prueba
no dependa de ninguna biblioteca de cripto: si el código a mano deja de cuadrar
con el estándar, esto se pone rojo.
"""

from __future__ import annotations

import unittest

from nucleo.billeteras import mensaje_de_desafio
from nucleo.firmas import (
    ErrorDeBilletera,
    base58_a_bytes,
    detectar_red,
    keccak256,
    red_de_ficha,
    verificar_evm,
    verificar_firma,
    verificar_solana,
)

CORREO = "ana@correo.com"
NONCE = "0123456789abcdef0123456789abcdef"
MENSAJE = mensaje_de_desafio(CORREO, NONCE)

EVM_DIRECCION = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"
EVM_FIRMA = ("9a1056e8e82574982c69abda8d3ed5234dd3b193a566e51fd103b301e0e3709d"
             "4b2aa9c58bd1f6255f3e620fa31aec9723ec41c58283884f99002ab4a213a5641b")

SOL_DIRECCION = "FAe4sisG95oZ42w7buUn5qEE4TAnfTTFPiguZUHmhiF"
SOL_FIRMA = ("5f956cc7c32db006a0cf7f0028dfacb36b1cb609dde7d59dc4f98fb8f4a28445"
             "1fbf4777a4fdbc2adcfbf8406b99017d9ffacb45832a017b7f3f06ef3d1e930e")


class KeccakTest(unittest.TestCase):
    def test_vectores_conocidos(self):
        self.assertEqual(
            keccak256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(
            keccak256(b"abc").hex(),
            "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_no_es_sha3(self):
        import hashlib
        self.assertNotEqual(keccak256(b"abc"), hashlib.sha3_256(b"abc").digest())


class EvmTest(unittest.TestCase):
    def test_firma_valida(self):
        self.assertTrue(verificar_evm(EVM_DIRECCION, MENSAJE, bytes.fromhex(EVM_FIRMA)))

    def test_firma_de_otro_mensaje_no_vale(self):
        self.assertFalse(verificar_evm(EVM_DIRECCION, MENSAJE + "x",
                                       bytes.fromhex(EVM_FIRMA)))

    def test_firma_manoseada_no_vale(self):
        firma = bytearray(bytes.fromhex(EVM_FIRMA))
        firma[10] ^= 1
        self.assertFalse(verificar_evm(EVM_DIRECCION, MENSAJE, bytes(firma)))

    def test_otra_direccion_no_vale(self):
        self.assertFalse(verificar_evm("0x" + "ab" * 20, MENSAJE,
                                       bytes.fromhex(EVM_FIRMA)))

    def test_firma_de_longitud_mala(self):
        with self.assertRaises(ErrorDeBilletera):
            verificar_evm(EVM_DIRECCION, MENSAJE, b"\x00" * 64)


class SolanaTest(unittest.TestCase):
    def test_firma_valida(self):
        self.assertTrue(verificar_solana(SOL_DIRECCION, MENSAJE,
                                         bytes.fromhex(SOL_FIRMA)))

    def test_firma_de_otro_mensaje_no_vale(self):
        self.assertFalse(verificar_solana(SOL_DIRECCION, MENSAJE + "x",
                                          bytes.fromhex(SOL_FIRMA)))

    def test_firma_manoseada_no_vale(self):
        firma = bytearray(bytes.fromhex(SOL_FIRMA))
        firma[5] ^= 1
        self.assertFalse(verificar_solana(SOL_DIRECCION, MENSAJE, bytes(firma)))

    def test_direccion_invalida_no_revienta(self):
        self.assertFalse(verificar_solana("no-es-base58-0OIl", MENSAJE,
                                          bytes.fromhex(SOL_FIRMA)))

    def test_firma_de_longitud_mala(self):
        with self.assertRaises(ErrorDeBilletera):
            verificar_solana(SOL_DIRECCION, MENSAJE, b"\x00" * 63)


class DeteccionTest(unittest.TestCase):
    def test_evm(self):
        self.assertEqual(detectar_red(EVM_DIRECCION), "evm")

    def test_solana(self):
        self.assertEqual(detectar_red(SOL_DIRECCION), "solana")

    def test_basura(self):
        with self.assertRaises(ErrorDeBilletera):
            detectar_red("no-es-una-direccion")

    def test_alias_de_red(self):
        self.assertEqual(red_de_ficha("polygon", EVM_DIRECCION), "evm")
        self.assertEqual(red_de_ficha("sol", SOL_DIRECCION), "solana")
        # Sin red, se adivina.
        self.assertEqual(red_de_ficha("", SOL_DIRECCION), "solana")

    def test_verificar_firma_elige_la_red(self):
        self.assertTrue(verificar_firma("evm", EVM_DIRECCION, MENSAJE,
                                        bytes.fromhex(EVM_FIRMA)))
        self.assertTrue(verificar_firma("solana", SOL_DIRECCION, MENSAJE,
                                        bytes.fromhex(SOL_FIRMA)))


class Base58Test(unittest.TestCase):
    def test_ida_y_vuelta(self):
        self.assertEqual(base58_a_bytes(SOL_DIRECCION).__len__(), 32)
        self.assertEqual(base58_a_bytes("1"), b"\x00")
        with self.assertRaises(ErrorDeBilletera):
            base58_a_bytes("0")  # el cero no está en el alfabeto base58


if __name__ == "__main__":
    unittest.main()
