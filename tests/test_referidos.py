"""Pruebas del sistema de referidos."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from nucleo.almacen import Almacen
from nucleo.monedero import Monedero
from nucleo.referidos import Referidos, porcentaje
from nucleo.usuarios import ErrorDeUsuario, Usuarios


class ReferidosTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.ref = Referidos(self.almacen)

    def _par(self):
        self.usuarios.registrar("padrino@x.com", "clave12345", "Padrino")
        codigo = self.ref.codigo_de("padrino@x.com")
        self.usuarios.registrar("ahijado@x.com", "clave12345", "Ahijado",
                                codigo_amigo=codigo)
        return codigo

    def test_al_registrarse_se_genera_un_codigo(self):
        self.usuarios.registrar("ana@x.com", "clave12345", "Ana")
        codigo = self.ref.codigo_de("ana@x.com")
        self.assertTrue(codigo)
        self.assertEqual(self.almacen.usuario_por_codigo(codigo)["correo"], "ana@x.com")

    def test_los_codigos_no_se_repiten(self):
        self.usuarios.registrar("pepe@x.com", "clave12345", "Pepe")
        self.usuarios.registrar("pepe2@x.com", "clave12345", "Pepe")
        self.assertNotEqual(self.ref.codigo_de("pepe@x.com"), self.ref.codigo_de("pepe2@x.com"))

    def test_una_cuenta_vieja_recibe_codigo_al_pedirlo(self):
        # Cuentas creadas antes de los referidos no traen código. Al pedirlo se
        # les genera uno, y no cambia si se vuelve a pedir.
        self.almacen.crear_usuario("vieja@x.com", "huella", "Vieja", "jugador", 1.0)
        self.assertEqual(self.ref.codigo_de("vieja@x.com"), "")
        codigo = self.usuarios.asegurar_codigo_amigo("vieja@x.com")
        self.assertTrue(codigo)
        self.assertEqual(self.ref.codigo_de("vieja@x.com"), codigo)
        self.assertEqual(self.usuarios.asegurar_codigo_amigo("vieja@x.com"), codigo)

    def test_la_cuenta_de_admin_tiene_codigo(self):
        # La de administración se crea por otro camino: también necesita código.
        self.usuarios.asegurar_admin("jefe@x.com", "ClaveAdmin123")
        codigo = self.usuarios.asegurar_codigo_amigo("jefe@x.com")
        self.assertTrue(codigo)
        self.assertEqual(self.almacen.usuario_por_codigo(codigo)["correo"], "jefe@x.com")

    def test_una_cuenta_que_no_existe_no_da_codigo(self):
        self.assertEqual(self.usuarios.asegurar_codigo_amigo("nadie@x.com"), "")

    def test_un_codigo_que_no_existe_falla(self):
        with self.assertRaises(ErrorDeUsuario):
            self.usuarios.registrar("tarde@x.com", "clave12345", "Tarde",
                                    codigo_amigo="NOEXISTE")

    def test_se_guarda_el_correo_del_padrino_no_el_codigo(self):
        codigo = self._par()
        self.assertEqual(self.ref.padrino_de("ahijado@x.com"), "padrino@x.com")
        # El ahijado tiene su propio código, distinto del que usó.
        self.assertTrue(self.ref.codigo_de("ahijado@x.com"))
        self.assertNotEqual(self.ref.codigo_de("ahijado@x.com"), codigo)

    def test_el_padrino_cobra_su_parte_de_la_app(self):
        self._par()
        pagos = self.ref.liquidar("p1", [{"correo": "ahijado@x.com", "puesto": 1}],
                                  {"app": 1000}, self.monedero)
        self.assertEqual(len(pagos), 1)
        # 10 % de 1000 = 100.
        self.assertEqual(self.monedero.saldo("padrino@x.com"), 100)

    def test_sin_padrino_no_se_paga_nada(self):
        self.usuarios.registrar("solo@x.com", "clave12345", "Solo")
        pagos = self.ref.liquidar("p1", [{"correo": "solo@x.com", "puesto": 1}],
                                  {"app": 1000}, self.monedero)
        self.assertEqual(pagos, [])
        self.assertEqual(self.monedero.saldo("solo@x.com"), 0)

    def test_reintentar_la_misma_partida_no_paga_dos_veces(self):
        self._par()
        self.ref.liquidar("p1", [{"correo": "ahijado@x.com", "puesto": 1}],
                          {"app": 1000}, self.monedero)
        self.ref.liquidar("p1", [{"correo": "ahijado@x.com", "puesto": 1}],
                          {"app": 1000}, self.monedero)
        self.assertEqual(self.monedero.saldo("padrino@x.com"), 100)

    def test_nunca_se_paga_mas_que_la_parte_de_la_app(self):
        # Varios ganadores apadrinados por el mismo padrino, con un evento de
        # varios puestos: el total pagado no puede pasar de la parte de la app.
        self._par()
        self.usuarios.registrar("ahijado2@x.com", "clave12345", "Ahijado2",
                                codigo_amigo=self.ref.codigo_de("padrino@x.com"))
        for i in range(1, 4):
            self.ref.liquidar(
                "p1", [{"correo": "ahijado@x.com", "puesto": i},
                       {"correo": "ahijado2@x.com", "puesto": i}],
                {"app": 100}, self.monedero)
        self.assertLessEqual(self.monedero.saldo("padrino@x.com"), 100)

    def test_el_porcentaje_se_ajusta_por_entorno(self):
        with patch.dict(os.environ, {"BINGO_REFERIDO_PCT": "25"}):
            self.assertEqual(porcentaje(), 25)
        with patch.dict(os.environ, {"BINGO_REFERIDO_PCT": "999"}):
            # Un valor absurdo cae al de por defecto, no revienta.
            self.assertEqual(porcentaje(), 10)

    def test_si_la_app_no_gana_no_se_paga_a_nadie(self):
        self._par()
        pagos = self.ref.liquidar("p1", [{"correo": "ahijado@x.com", "puesto": 1}],
                                  {"app": 0}, self.monedero)
        self.assertEqual(pagos, [])

    def test_el_resumen_del_jugador_cuenta_lo_suyo(self):
        self._par()
        self.ref.liquidar("p1", [{"correo": "ahijado@x.com", "puesto": 1}],
                          {"app": 1000}, self.monedero)
        r = self.ref.resumen("padrino@x.com")
        self.assertEqual(r["invitados"], 1)
        self.assertEqual(r["total"], 100)
        self.assertEqual(r["pct"], 10)


if __name__ == "__main__":
    unittest.main()
