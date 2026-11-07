"""Pruebas de usuarios: registro propio, roles y sesiones en la base de datos."""

from __future__ import annotations

import unittest

from nucleo import Almacen, Usuarios, hash_clave, verificar_clave
from nucleo.usuarios import ErrorDeUsuario


class ClaveTest(unittest.TestCase):
    def test_la_huella_no_guarda_la_clave(self):
        h = hash_clave("miClaveSegura1")
        self.assertNotIn("miClaveSegura1", h)
        self.assertIn("$", h)

    def test_la_sal_cambia_cada_vez(self):
        self.assertNotEqual(hash_clave("miClaveSegura1"), hash_clave("miClaveSegura1"))

    def test_verificar_acepta_la_buena_y_rechaza_la_mala(self):
        h = hash_clave("miClaveSegura1")
        self.assertTrue(verificar_clave("miClaveSegura1", h))
        self.assertFalse(verificar_clave("otraClave123", h))
        self.assertFalse(verificar_clave("miClaveSegura1", "basura"))


class RegistroTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.u = Usuarios(self.almacen)

    def tearDown(self):
        self.almacen.cerrar()

    def test_registrar_y_entrar(self):
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        sesion = self.u.entrar("ana@correo.com", "miClaveSegura1")
        self.assertTrue(sesion.token)
        self.assertIsNotNone(self.u.sesion(sesion.token))

    def test_el_correo_no_distingue_mayusculas(self):
        self.u.registrar("Ana@Correo.com", "miClaveSegura1")
        sesion = self.u.entrar("ana@correo.com", "miClaveSegura1")
        self.assertEqual(sesion.correo, "ana@correo.com")

    def test_no_se_repite_el_correo(self):
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        with self.assertRaises(ErrorDeUsuario):
            self.u.registrar("ana@correo.com", "otraClave123")

    def test_correo_mal_formado(self):
        for malo in ("", "ana", "ana@", "@correo.com", "ana correo.com"):
            with self.assertRaises(ErrorDeUsuario):
                self.u.registrar(malo, "miClaveSegura1")

    def test_clave_corta_o_comun(self):
        for mala in ("corta", "12345678", "password"):
            with self.assertRaises(ErrorDeUsuario):
                self.u.registrar("ana@correo.com", mala)

    def test_quien_se_registra_es_jugador(self):
        u = self.u.registrar("ana@correo.com", "miClaveSegura1")
        self.assertEqual(u.rol, "jugador")
        self.assertFalse(self.u.es_admin("ana@correo.com"))

    def test_el_admin_se_crea_y_es_admin(self):
        creado = self.u.asegurar_admin("bingopiramide777@gmail.com", "ClaveAdmin123")
        self.assertTrue(creado)
        self.assertTrue(self.u.es_admin("bingopiramide777@gmail.com"))
        # La segunda vez no lo vuelve a crear ni cambia la clave.
        self.assertFalse(self.u.asegurar_admin("bingopiramide777@gmail.com", "OtraClave456"))
        self.u.entrar("bingopiramide777@gmail.com", "ClaveAdmin123")

    def test_clave_equivocada_no_entra(self):
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        with self.assertRaises(ErrorDeUsuario):
            self.u.entrar("ana@correo.com", "otraClave999")

    def test_bloqueo_tras_varios_intentos(self):
        self.u = Usuarios(self.almacen, max_intentos=3, minutos_bloqueo=15)
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        for _ in range(3):
            with self.assertRaises(ErrorDeUsuario):
                self.u.entrar("ana@correo.com", "mal")
        with self.assertRaises(ErrorDeUsuario):
            self.u.entrar("ana@correo.com", "miClaveSegura1")

    def test_la_sesion_sobrevive_al_reinicio(self):
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        sesion = self.u.entrar("ana@correo.com", "miClaveSegura1")
        otro = Usuarios(self.almacen)
        self.assertIsNotNone(otro.sesion(sesion.token))

    def test_desactivar_impide_entrar(self):
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        self.u.activar("ana@correo.com", False)
        with self.assertRaises(ErrorDeUsuario):
            self.u.entrar("ana@correo.com", "miClaveSegura1")

    def test_salir_invalida_la_sesion(self):
        self.u.registrar("ana@correo.com", "miClaveSegura1")
        sesion = self.u.entrar("ana@correo.com", "miClaveSegura1")
        self.u.salir(sesion.token)
        self.assertIsNone(self.u.sesion(sesion.token))

    def test_token_inventado_no_vale(self):
        self.assertIsNone(self.u.sesion("token-inventado"))


if __name__ == "__main__":
    unittest.main()
