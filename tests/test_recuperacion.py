"""Pruebas de recuperación de cuenta: código por correo y pregunta secreta."""

from __future__ import annotations

import unittest

from nucleo import Almacen, Usuarios
from nucleo.correo import Correo
from nucleo.usuarios import ErrorDeUsuario, PREGUNTAS


class PreguntaSecretaTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.u = Usuarios(self.almacen)
        self.u.registrar("ana@correo.com", "miClaveSegura1", "Ana",
                         "jugador", PREGUNTAS[0], "Firulais")

    def tearDown(self):
        self.almacen.cerrar()

    def test_guarda_la_pregunta(self):
        self.assertEqual(self.u.pregunta_de("ana@correo.com"), PREGUNTAS[0])

    def test_la_respuesta_no_se_guarda_en_claro(self):
        fila = self.almacen.usuario("ana@correo.com")
        self.assertNotIn("Firulais", fila["respuesta_huella"])
        self.assertNotIn("firulais", fila["respuesta_huella"])

    def test_cambia_la_clave_con_la_respuesta(self):
        self.u.cambiar_con_respuesta("ana@correo.com", "Firulais", "ClaveNueva123")
        self.u.entrar("ana@correo.com", "ClaveNueva123")

    def test_la_respuesta_no_distingue_mayusculas_ni_tildes(self):
        for escrito in ("firulais", "FIRULAIS", "  Firulais  ", "Firuláis"):
            self.assertTrue(self.u.verificar_respuesta("ana@correo.com", escrito),
                            f"debería aceptar {escrito!r}")

    def test_respuesta_mala_no_cambia_nada(self):
        with self.assertRaises(ErrorDeUsuario):
            self.u.cambiar_con_respuesta("ana@correo.com", "otra cosa", "ClaveNueva123")
        # La clave vieja sigue valiendo.
        self.u.entrar("ana@correo.com", "miClaveSegura1")

    def test_pregunta_de_un_correo_que_no_existe(self):
        self.assertIsNone(self.u.pregunta_de("nadie@correo.com"))

    def test_pregunta_inventada_se_rechaza(self):
        with self.assertRaises(ErrorDeUsuario):
            self.u.registrar("luis@correo.com", "miClaveSegura1", "Luis",
                             "jugador", "¿Cuál es tu color favorito?", "azul")


class CodigoTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.u = Usuarios(self.almacen)
        self.u.registrar("ana@correo.com", "miClaveSegura1")

    def tearDown(self):
        self.almacen.cerrar()

    def test_el_codigo_tiene_seis_cifras(self):
        codigo = self.u.pedir_codigo("ana@correo.com")
        self.assertEqual(len(codigo), 6)
        self.assertTrue(codigo.isdigit())

    def test_el_codigo_no_se_guarda_en_claro(self):
        codigo = self.u.pedir_codigo("ana@correo.com")
        fila = self.almacen.codigo_pendiente("ana@correo.com")
        self.assertNotEqual(fila["huella"], codigo)
        self.assertNotIn(codigo, fila["huella"])

    def test_cambia_la_clave_con_el_codigo(self):
        codigo = self.u.pedir_codigo("ana@correo.com")
        self.u.cambiar_con_codigo("ana@correo.com", codigo, "ClaveNueva123")
        self.u.entrar("ana@correo.com", "ClaveNueva123")

    def test_el_codigo_solo_sirve_una_vez(self):
        codigo = self.u.pedir_codigo("ana@correo.com")
        self.u.cambiar_con_codigo("ana@correo.com", codigo, "ClaveNueva123")
        with self.assertRaises(ErrorDeUsuario):
            self.u.cambiar_con_codigo("ana@correo.com", codigo, "OtraClave456")

    def test_un_codigo_nuevo_anula_el_anterior(self):
        viejo = self.u.pedir_codigo("ana@correo.com")
        nuevo = self.u.pedir_codigo("ana@correo.com")
        with self.assertRaises(ErrorDeUsuario):
            self.u.cambiar_con_codigo("ana@correo.com", viejo, "ClaveNueva123")
        self.u.cambiar_con_codigo("ana@correo.com", nuevo, "ClaveNueva123")

    def test_el_codigo_caduca(self):
        self.u.pedir_codigo("ana@correo.com", minutos=-1)
        fila = self.almacen.codigo_pendiente("ana@correo.com")
        with self.assertRaises(ErrorDeUsuario):
            self.u.cambiar_con_codigo("ana@correo.com", "000000", "ClaveNueva123")
        self.assertIsNotNone(fila)

    def test_codigo_malo_gasta_intentos_y_se_anula(self):
        self.u.pedir_codigo("ana@correo.com")
        for i in range(5):
            with self.assertRaises(ErrorDeUsuario):
                self.u.cambiar_con_codigo("ana@correo.com", "999999", "ClaveNueva123")
        # Ya no queda código pendiente: hay que pedir otro.
        self.assertIsNone(self.almacen.codigo_pendiente("ana@correo.com"))

    def test_tope_de_codigos_por_hora(self):
        for _ in range(3):
            self.u.pedir_codigo("ana@correo.com")
        with self.assertRaises(ErrorDeUsuario):
            self.u.pedir_codigo("ana@correo.com")

    def test_correo_inexistente_no_revela_nada(self):
        """Pedir código para un correo sin cuenta no falla: devuelve vacío.

        Así nadie puede usar esta pantalla para averiguar qué correos están dados
        de alta.
        """
        self.assertEqual(self.u.pedir_codigo("nadie@correo.com"), "")
        self.assertIsNone(self.almacen.codigo_pendiente("nadie@correo.com"))


class SesionesTest(unittest.TestCase):
    """Lo importante: al cambiar la contraseña se cierran TODAS las sesiones."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.u = Usuarios(self.almacen)
        self.u.registrar("ana@correo.com", "miClaveSegura1", "Ana",
                         "jugador", PREGUNTAS[0], "Firulais")

    def tearDown(self):
        self.almacen.cerrar()

    def test_cambiar_la_clave_cierra_las_sesiones(self):
        s1 = self.u.entrar("ana@correo.com", "miClaveSegura1")
        s2 = self.u.entrar("ana@correo.com", "miClaveSegura1")
        self.assertIsNotNone(self.u.sesion(s1.token))
        self.assertIsNotNone(self.u.sesion(s2.token))

        self.u.cambiar_clave("ana@correo.com", "ClaveNueva123")

        self.assertIsNone(self.u.sesion(s1.token), "la sesión vieja debe quedar cerrada")
        self.assertIsNone(self.u.sesion(s2.token), "la sesión vieja debe quedar cerrada")

    def test_el_admin_tambien_cierra_sesiones(self):
        sesion = self.u.entrar("ana@correo.com", "miClaveSegura1")
        self.u.restablecer_por_admin("ana@correo.com", "ClaveTemporal99")
        self.assertIsNone(self.u.sesion(sesion.token))
        self.u.entrar("ana@correo.com", "ClaveTemporal99")

    def test_las_sesiones_de_otro_no_se_tocan(self):
        self.u.registrar("luis@correo.com", "miClaveSegura1")
        ana = self.u.entrar("ana@correo.com", "miClaveSegura1")
        luis = self.u.entrar("luis@correo.com", "miClaveSegura1")
        self.u.cambiar_clave("ana@correo.com", "ClaveNueva123")
        self.assertIsNone(self.u.sesion(ana.token))
        self.assertIsNotNone(self.u.sesion(luis.token))


class CorreoTest(unittest.TestCase):
    def test_sin_configurar_no_miente(self):
        """Sin clave configurada no puede decir que ha enviado: devuelve False."""
        c = Correo(usuario="", clave="")
        self.assertFalse(c.configurado)
        self.assertFalse(c.enviar("ana@correo.com", "Asunto", "Texto"))

    def test_con_configuracion_dice_que_esta_configurado(self):
        c = Correo(usuario="a@b.com", clave="abcdefghijklmnop")
        self.assertTrue(c.configurado)


if __name__ == "__main__":
    unittest.main()
