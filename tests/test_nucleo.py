"""Pruebas del núcleo: dinero exacto y monedero. Lo comparten los juegos."""

from __future__ import annotations

import unittest

from nucleo import ErrorDeMonedero, Monedero, a_centimos, a_texto


class DineroTest(unittest.TestCase):
    def test_centimos_exactos(self):
        self.assertEqual(a_centimos("10.50"), 1_050)
        self.assertEqual(a_centimos("10,50"), 1_050)
        self.assertEqual(a_centimos(10.5), 1_050)
        self.assertEqual(a_centimos("0.01"), 1)

    def test_el_error_de_float_no_aparece(self):
        # 0.1 + 0.2 en float daría 0.30000000000000004
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
        self.m = Monedero()

    def test_recargar_y_consultar(self):
        self.m.recargar("ana", 5_000)
        self.assertEqual(self.m.saldo("ana"), 5_000)

    def test_no_se_puede_gastar_lo_que_no_hay(self):
        with self.assertRaises(ErrorDeMonedero):
            self.m.retirar("ana", 1_000)
        self.assertEqual(self.m.saldo("ana"), 0)

    def test_movimiento_de_cero_no_vale(self):
        with self.assertRaises(ErrorDeMonedero):
            self.m.recargar("ana", 0)

    def test_no_admite_texto_ni_decimales_sueltos(self):
        # Si alguien pasa "10.00" en vez de 1000, es un error de programa y se avisa.
        for malo in ("10.00", 10.5, True, None):
            with self.assertRaises(ErrorDeMonedero):
                self.m.recargar("ana", malo)

    def test_el_historial_guarda_el_rastro(self):
        self.m.recargar("ana", 10_000)
        self.m.cobrar_apuesta("ana", 1_000, "cartón x")
        self.m.pagar_premio("ana", 30_000, "bingo")
        hist = self.m.historial("ana")
        self.assertEqual([m.tipo for m in hist], ["recarga", "apuesta", "premio"])
        self.assertEqual([m.centimos for m in hist], [10_000, -1_000, 30_000])
        self.assertEqual(hist[-1].saldo_despues, 39_000)

    def test_el_saldo_nunca_queda_negativo(self):
        self.m.recargar("ana", 1_000)
        with self.assertRaises(ErrorDeMonedero):
            self.m.retirar("ana", 1_001)
        self.assertEqual(self.m.saldo("ana"), 1_000)

    def test_saldos_separados_por_jugador(self):
        self.m.recargar("ana", 1_000)
        self.m.recargar("luis", 2_000)
        self.assertEqual(self.m.saldo("ana"), 1_000)
        self.assertEqual(self.m.saldo("luis"), 2_000)


if __name__ == "__main__":
    unittest.main()
