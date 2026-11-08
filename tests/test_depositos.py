"""Pruebas de depósitos: declarar, acreditar, rechazar y los frenos."""

from __future__ import annotations

import unittest

from nucleo import Almacen, Monedero, Usuarios
from nucleo.depositos import (BANCOS, ConfigDeposito, CuentaDePago, Depositos,
                              ErrorDeDeposito, hoy)


class DepositoTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.depositos = Depositos(self.almacen, self.monedero,
                                   ConfigDeposito(minimo=1_000, tope_diario=1_000_000))
        self.correo = "ana@correo.com"
        self.usuarios.registrar(self.correo, "miClaveSegura1")

    def tearDown(self):
        self.almacen.cerrar()

    def declarar(self, importe="100,00", referencia="123456", **extra):
        datos = dict(importe=importe, referencia=referencia, banco="Banco de Venezuela",
                     dia=hoy(), metodo="pago_movil")
        datos.update(extra)
        return self.depositos.declarar(self.correo, **datos)

    def test_declarar_no_acredita_todavia(self):
        d = self.declarar()
        self.assertEqual(d.estado, "pendiente")
        self.assertEqual(d.centimos, 10_000)
        self.assertEqual(self.monedero.saldo(self.correo), 0)

    # -- cuenta a la que se paga --

    def test_la_cuenta_de_pago_esta_configurada_por_defecto(self):
        cuenta = ConfigDeposito().cuenta
        self.assertTrue(cuenta.configurada)
        self.assertEqual(cuenta.banco, "Banco de Venezuela")
        self.assertTrue(cuenta.telefono)
        self.assertTrue(cuenta.cedula)

    def test_la_cuenta_de_pago_se_puede_cambiar_por_entorno(self):
        import os
        from unittest.mock import patch
        entorno = {"BINGO_PAGO_BANCO": "Banesco", "BINGO_PAGO_TELEFONO": "0414-0000000",
                   "BINGO_PAGO_CEDULA": "1.111.111", "BINGO_PAGO_TITULAR": "Ana Pérez"}
        with patch.dict(os.environ, entorno):
            cuenta = CuentaDePago.desde_entorno()
        self.assertEqual(cuenta.banco, "Banesco")
        self.assertEqual(cuenta.telefono, "0414-0000000")
        self.assertEqual(cuenta.cedula, "1.111.111")
        self.assertEqual(cuenta.titular, "Ana Pérez")

    def test_la_cuenta_sin_datos_no_se_ofrece(self):
        cuenta = CuentaDePago(telefono="", cedula="")
        self.assertFalse(cuenta.configurada)

    def test_la_cuenta_publica_no_lleva_mas_que_lo_necesario(self):
        datos = CuentaDePago().a_dict()
        self.assertEqual(set(datos), {"banco", "telefono", "cedula", "titular", "configurada"})

    def test_acreditar_suma_el_dinero(self):
        d = self.declarar()
        acreditado = self.depositos.acreditar(d.id, "admin@correo.com", "verificado")
        self.assertEqual(acreditado.estado, "acreditado")
        self.assertEqual(self.monedero.saldo(self.correo), 10_000)

    def test_no_se_acredita_dos_veces(self):
        d = self.declarar()
        self.depositos.acreditar(d.id, "admin@correo.com")
        with self.assertRaises(ErrorDeDeposito):
            self.depositos.acreditar(d.id, "admin@correo.com")
        self.assertEqual(self.monedero.saldo(self.correo), 10_000)

    def test_rechazar_no_mueve_dinero(self):
        d = self.declarar()
        self.depositos.rechazar(d.id, "admin@correo.com", "referencia no aparece")
        self.assertEqual(self.monedero.saldo(self.correo), 0)

    def test_la_misma_referencia_no_vale_dos_veces_el_mismo_dia(self):
        """El freno contra reenviar la misma captura de pantalla."""
        self.declarar(referencia="999888")
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(referencia="999888")
        self.assertEqual(len(self.depositos.pendientes()), 1)

    def test_una_referencia_rechazada_se_puede_volver_a_usar(self):
        d = self.declarar(referencia="555444")
        self.depositos.rechazar(d.id, "admin@correo.com")
        self.declarar(referencia="555444")  # ahora sí
        self.assertEqual(len(self.depositos.pendientes()), 1)

    def test_la_referencia_son_solo_numeros(self):
        for mala in ("abc123", "12", "", "1234-5678", "123456789012345678901"):
            with self.assertRaises(ErrorDeDeposito):
                self.declarar(referencia=mala)

    def test_banco_tiene_que_ser_de_la_lista(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(banco="Banco Inventado")
        self.assertIn("Banco de Venezuela", BANCOS)

    def test_metodo_valido(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(metodo="bitcoin")
        self.declarar(metodo="transferencia")

    def test_minimo(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(importe="5,00")

    def test_tope_diario(self):
        self.declarar(importe="9000,00", referencia="111111")
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(importe="9000,00", referencia="222222")

    def test_la_fecha_no_puede_ser_futura(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(dia="2030-01-01")

    def test_la_fecha_no_puede_ser_muy_vieja(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(dia="2020-01-01")

    def test_la_fecha_tiene_que_tener_formato(self):
        for mala in ("hoy", "01/01/2026", "2026-13-45"):
            with self.assertRaises(ErrorDeDeposito):
                self.declarar(dia=mala)

    def test_cuenta_inexistente_no_puede_declarar(self):
        with self.assertRaises(ErrorDeDeposito):
            self.depositos.declarar("nadie@correo.com", "100,00", "123456",
                                    "Banco de Venezuela", hoy())

    def test_los_depositos_sobreviven_al_reinicio(self):
        d = self.declarar()
        otros = Depositos(self.almacen, self.monedero, self.depositos.config)
        self.assertEqual(len(otros.pendientes()), 1)
        self.assertEqual(otros.pendientes()[0].id, d.id)

    def test_resumen_de_pendientes(self):
        self.declarar(importe="50,00", referencia="777777")
        self.declarar(importe="30,00", referencia="888888")
        self.assertEqual(len(self.depositos.pendientes()), 2)
        self.assertEqual(self.depositos.total_pendiente(), 8_000)

    # -- multi-país --

    def test_metodos_internacionales_valen(self):
        for metodo in ("nequi", "mach", "cashapp"):
            # En Colombia el mínimo son 1.000 pesos: el importe va en pesos.
            self.depositos.declarar(self.correo, "1000,00", f"9{abs(hash(metodo)) % 100000:05d}",
                                    "", hoy(), metodo, "", "CO")
            self.assertEqual(self.depositos.pendientes()[0].metodo, metodo)

    def test_los_metodos_sin_banco_no_piden_banco(self):
        d = self.depositos.declarar(self.correo, "1000,00", "123123", "", hoy(),
                                    "nequi", "", "CO")
        self.assertEqual(d.banco, "")
        self.assertEqual(d.pais, "CO")

    def test_el_importe_se_guarda_en_la_moneda_base(self):
        # 1.000 pesos colombianos, con tasa 0,01, son 10 bolívares = 1.000 céntimos.
        d = self.depositos.declarar(self.correo, "1000,00", "555111", "", hoy(),
                                    "nequi", "", "CO")
        self.assertEqual(d.centimos, 1_000)

    def test_los_metodos_de_banco_siguen_pidiendo_banco(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(banco="", metodo="pago_movil")

    def test_un_pais_desconocido_se_rechaza(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(pais="XX")

    def test_el_pais_por_defecto_es_venezuela(self):
        d = self.declarar()
        self.assertEqual(d.pais, "VE")

    def test_el_pais_se_guarda_y_se_recupera(self):
        d = self.depositos.declarar(self.correo, "100,00", "456456", "", hoy(),
                                    "cashapp", "", "US")
        otro = Depositos(self.almacen, self.monedero, self.depositos.config)
        guardado = next(x for x in otro.pendientes() if x.id == d.id)
        self.assertEqual(guardado.pais, "US")


if __name__ == "__main__":
    unittest.main()
