"""Pruebas de depósitos: declarar, acreditar, rechazar y los frenos."""

from __future__ import annotations

import unittest

from nucleo import Almacen, Monedero, Usuarios
from nucleo.depositos import METODOS, ConfigDeposito, Depositos, ErrorDeDeposito, hoy


class DepositoTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.depositos = Depositos(self.almacen, self.monedero,
                                   ConfigDeposito(minimo=100, tope_diario=100_000))
        self.correo = "ana@correo.com"
        self.usuarios.registrar(self.correo, "miClaveSegura1")

    def tearDown(self):
        self.almacen.cerrar()

    def declarar(self, importe="10,00", referencia="123456", **extra):
        datos = dict(importe=importe, referencia=referencia, banco="",
                     dia=hoy(), metodo="paypal")
        datos.update(extra)
        return self.depositos.declarar(self.correo, **datos)

    def test_declarar_no_acredita_todavia(self):
        d = self.declarar()
        self.assertEqual(d.estado, "pendiente")
        self.assertEqual(d.centimos, 1_000)
        self.assertEqual(self.monedero.saldo(self.correo), 0)

    def test_acreditar_suma_el_dinero(self):
        d = self.declarar()
        acreditado = self.depositos.acreditar(d.id, "admin@correo.com", "verificado")
        self.assertEqual(acreditado.estado, "acreditado")
        self.assertEqual(self.monedero.saldo(self.correo), 1_000)

    def test_no_se_acredita_dos_veces(self):
        d = self.declarar()
        self.depositos.acreditar(d.id, "admin@correo.com")
        with self.assertRaises(ErrorDeDeposito):
            self.depositos.acreditar(d.id, "admin@correo.com")
        self.assertEqual(self.monedero.saldo(self.correo), 1_000)

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

    def test_la_referencia_admite_letras_y_numeros(self):
        # Un id de transacción de PayPal o un hash de USDT no son solo números.
        self.declarar(referencia="5TYX9A2BC-77")
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(referencia="12")  # demasiado corta

    def test_metodo_valido(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(metodo="bitcoin")
        self.declarar(metodo="paypal")
        self.declarar(metodo="cripto", referencia="otra-ref-1")

    def test_minimo(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(importe="0,50")

    def test_tope_diario(self):
        self.declarar(importe="900,00", referencia="111111")
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(importe="900,00", referencia="222222")

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
                                    "", hoy())

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

    # -- métodos y países --

    def test_solo_hay_paypal_y_cripto(self):
        self.assertEqual(METODOS, ("paypal", "cripto"))

    def test_paypal_y_cripto_valen(self):
        for metodo in ("paypal", "cripto"):
            d = self.depositos.declarar(self.correo, "10,00",
                                        f"ref-{metodo}", "", hoy(), metodo, "", "CO")
            self.assertEqual(d.metodo, metodo)

    def test_no_hay_conversion_de_moneda(self):
        # 10 dólares son 1.000 céntimos, en cualquier país.
        d = self.depositos.declarar(self.correo, "10,00", "555111", "", hoy(),
                                    "paypal", "", "CO")
        self.assertEqual(d.centimos, 1_000)

    def test_un_pais_desconocido_se_rechaza(self):
        with self.assertRaises(ErrorDeDeposito):
            self.declarar(pais="XX")

    def test_el_pais_por_defecto_es_venezuela(self):
        d = self.declarar()
        self.assertEqual(d.pais, "VE")

    def test_el_pais_se_guarda_y_se_recupera(self):
        d = self.depositos.declarar(self.correo, "10,00", "456456", "", hoy(),
                                    "cripto", "", "US")
        otro = Depositos(self.almacen, self.monedero, self.depositos.config)
        guardado = next(x for x in otro.pendientes() if x.id == d.id)
        self.assertEqual(guardado.pais, "US")


if __name__ == "__main__":
    unittest.main()
