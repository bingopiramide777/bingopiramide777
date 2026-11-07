"""Pruebas del núcleo: dinero exacto, base de datos y monedero."""

from __future__ import annotations

import unittest

from nucleo import Almacen, ErrorDeMonedero, Monedero, a_centimos, a_texto


class DineroTest(unittest.TestCase):
    def test_centimos_exactos(self):
        self.assertEqual(a_centimos("10.50"), 1_050)
        self.assertEqual(a_centimos("10,50"), 1_050)
        self.assertEqual(a_centimos(10.5), 1_050)
        self.assertEqual(a_centimos("0.01"), 1)

    def test_el_error_de_float_no_aparece(self):
        self.assertEqual(a_centimos("0.1") + a_centimos("0.2"), a_centimos("0.3"))
        self.assertEqual(a_texto(30), "Bs 0,30")

    def test_importes_invalidos(self):
        for malo in ("", "abc", "-5", None, True, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                a_centimos(malo)

    def test_formato_venezolano(self):
        self.assertEqual(a_texto(123_450), "Bs 1.234,50")
        self.assertEqual(a_texto(0), "Bs 0,00")


class MonederoTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.m = Monedero(self.almacen)

    def tearDown(self):
        self.almacen.cerrar()

    def test_recargar_y_consultar(self):
        self.m.recargar("ana@correo.com", 5_000)
        self.assertEqual(self.m.saldo("ana@correo.com"), 5_000)

    def test_no_se_puede_gastar_lo_que_no_hay(self):
        with self.assertRaises(ErrorDeMonedero):
            self.m.retirar("ana@correo.com", 1_000)
        self.assertEqual(self.m.saldo("ana@correo.com"), 0)

    def test_movimiento_de_cero_no_vale(self):
        with self.assertRaises(ErrorDeMonedero):
            self.m.recargar("ana@correo.com", 0)

    def test_no_admite_texto_ni_decimales_sueltos(self):
        for malo in ("10.00", 10.5, True, None):
            with self.assertRaises(ErrorDeMonedero):
                self.m.recargar("ana@correo.com", malo)

    def test_el_historial_guarda_el_rastro(self):
        self.m.recargar("ana@correo.com", 10_000)
        self.m.cobrar_apuesta("ana@correo.com", 1_000, "cartón x")
        self.m.pagar_premio("ana@correo.com", 30_000, "bingo")
        hist = self.m.historial("ana@correo.com")
        self.assertEqual([h.tipo for h in hist], ["premio", "apuesta", "recarga"])
        self.assertEqual(hist[-1].saldo_despues, 10_000)

    def test_el_saldo_nunca_queda_negativo(self):
        self.m.recargar("ana@correo.com", 1_000)
        with self.assertRaises(ErrorDeMonedero):
            self.m.retirar("ana@correo.com", 1_001)
        self.assertEqual(self.m.saldo("ana@correo.com"), 1_000)

    def test_saldos_separados_por_jugador(self):
        self.m.recargar("ana@correo.com", 1_000)
        self.m.recargar("luis@correo.com", 2_000)
        self.assertEqual(self.m.saldo("ana@correo.com"), 1_000)
        self.assertEqual(self.m.saldo("luis@correo.com"), 2_000)

    def test_el_saldo_sobrevive_al_reinicio(self):
        """Lo más importante: cerrar y reabrir la base no pierde el dinero."""
        import os, tempfile

        ruta = os.path.join(tempfile.mkdtemp(), "prueba.db")
        a1 = Almacen(ruta)
        Monedero(a1).recargar("ana@correo.com", 7_500)
        a1.cerrar()

        a2 = Almacen(ruta)
        self.assertEqual(Monedero(a2).saldo("ana@correo.com"), 7_500)
        a2.cerrar()


if __name__ == "__main__":
    unittest.main()
