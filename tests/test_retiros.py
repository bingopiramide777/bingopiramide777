"""Pruebas de retiros: pedir, pagar y rechazar (con devolución)."""

from __future__ import annotations

import unittest

from nucleo import Almacen, Monedero, Usuarios
from nucleo.retiros import ConfigRetiro, ErrorDeRetiro, Retiros


class RetiroTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.config = ConfigRetiro(minimo=5_000, tope_diario=1_000_000)
        self.retiros = Retiros(self.almacen, self.monedero, self.config)
        self.correo = "ana@correo.com"
        self.usuarios.registrar(self.correo, "miClaveSegura1")
        self.usuarios.asegurar_admin("admin@correo.com", "ClaveAdmin123")
        self.monedero.recargar(self.correo, 100_000)

    def tearDown(self):
        self.almacen.cerrar()

    def test_pedir_descuenta_el_saldo(self):
        r = self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        self.assertEqual(r.centimos, 5_000)
        self.assertEqual(r.estado, "pendiente")
        self.assertEqual(self.monedero.saldo(self.correo), 95_000)

    def test_no_se_puede_pedir_mas_que_el_saldo(self):
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.pedir(self.correo, "2000,00", "transferencia", "Banco X, cuenta 123")
        self.assertEqual(self.monedero.saldo(self.correo), 100_000)

    def test_minimo(self):
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.pedir(self.correo, "10,00", "transferencia", "Banco X, cuenta 123")

    def test_metodo_no_valido(self):
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.pedir(self.correo, "50,00", "bitcoin_magico", "algo")

    def test_hacen_falta_datos_de_cobro(self):
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.pedir(self.correo, "50,00", "transferencia", "")

    def test_tope_diario(self):
        # Tope diario de Bs 10.000 (1.000.000 céntimos). Con Bs 8.000 se pasa.
        self.monedero.recargar(self.correo, 1_000_000)
        self.retiros.pedir(self.correo, "8000,00", "transferencia", "Banco X, cuenta 123")
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.pedir(self.correo, "8000,00", "transferencia", "Banco X, cuenta 123")

    def test_pagar_no_vuelve_a_mover_el_saldo(self):
        r = self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        saldo = self.monedero.saldo(self.correo)
        pagado = self.retiros.pagar(r.id, "admin@correo.com", "hecho")
        self.assertEqual(pagado.estado, "pagado")
        self.assertEqual(self.monedero.saldo(self.correo), saldo)

    def test_rechazar_devuelve_el_dinero(self):
        r = self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        self.assertEqual(self.monedero.saldo(self.correo), 95_000)
        self.retiros.rechazar(r.id, "admin@correo.com", "datos malos")
        self.assertEqual(self.monedero.saldo(self.correo), 100_000)

    def test_no_se_resuelve_dos_veces(self):
        r = self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        self.retiros.pagar(r.id, "admin@correo.com")
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.pagar(r.id, "admin@correo.com")
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.rechazar(r.id, "admin@correo.com")

    def test_rechazar_dos_veces_no_devuelve_dos_veces(self):
        r = self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        self.retiros.rechazar(r.id, "admin@correo.com")
        saldo = self.monedero.saldo(self.correo)
        with self.assertRaises(ErrorDeRetiro):
            self.retiros.rechazar(r.id, "admin@correo.com")
        self.assertEqual(self.monedero.saldo(self.correo), saldo)

    def test_listar_pendientes(self):
        self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        self.assertEqual(len(self.retiros.pendientes()), 1)
        self.assertEqual(self.retiros.total_pendiente(), 5_000)

    def test_los_retiros_sobreviven_al_reinicio(self):
        r = self.retiros.pedir(self.correo, "50,00", "transferencia", "Banco X, cuenta 123")
        otros = Retiros(self.almacen, Monedero(self.almacen), self.config)
        self.assertEqual(len(otros.pendientes()), 1)
        self.assertEqual(otros.pendientes()[0].id, r.id)


if __name__ == "__main__":
    unittest.main()
