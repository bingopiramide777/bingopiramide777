"""Pruebas de la ficha de cobro (nucleo/datos_cobro.py y nucleo/fichas.py).

Lo importante: que los datos de cobro se guarden CIFRADOS (que quien lea la
base de datos no vea un número de cuenta) y que se puedan recuperar enteros.
"""

from __future__ import annotations

import unittest

from nucleo import Almacen, Usuarios
from nucleo.datos_cobro import (
    ErrorDeDatosCobro,
    FichaCobro,
    deserializar,
    resumen_publico,
    serializar,
    validar,
)
from nucleo.fichas import ErrorDeFicha, FichasCobro
from nucleo.salas import Salas
from nucleo.secretos import descifrar


class TestValidacion(unittest.TestCase):
    def test_metodo_no_valido(self):
        with self.assertRaises(ErrorDeDatosCobro):
            validar("pago_movil", {})

    def test_falta_un_campo_obligatorio(self):
        with self.assertRaises(ErrorDeDatosCobro):
            validar("paypal", {"titular": "Ana"})

    def test_paypal_completo(self):
        campos = validar("paypal", {"titular": "Ana Pérez", "correo": "ana@correo.com"})
        self.assertEqual(campos["correo"], "ana@correo.com")
        self.assertEqual(campos["titular"], "Ana Pérez")

    def test_cripto_completo(self):
        campos = validar("cripto", {"titular": "Luis", "red": "TRC-20 (Tron)",
                                    "direccion": "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"})
        self.assertEqual(campos["direccion"], "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE")
        self.assertEqual(campos["red"], "TRC-20 (Tron)")

    def test_correo_mal_formado_se_rechaza(self):
        with self.assertRaises(ErrorDeDatosCobro):
            validar("paypal", {"titular": "Ana", "correo": "no-es-un-correo"})

    def test_direccion_mal_formada_se_rechaza(self):
        with self.assertRaises(ErrorDeDatosCobro):
            validar("cripto", {"titular": "Ana", "red": "TRC-20", "direccion": "corta"})

    def test_se_descartan_campos_que_no_aplican(self):
        campos = validar("paypal", {"titular": "Ana", "correo": "a@b.com", "banco": "Banesco"})
        self.assertNotIn("banco", campos)


class TestSerializacion(unittest.TestCase):
    def test_ida_y_vuelta(self):
        metodo, campos = deserializar(serializar("nequi", {"titular": "Ana", "telefono": "300"}))
        self.assertEqual(metodo, "nequi")
        self.assertEqual(campos["titular"], "Ana")

    def test_texto_vacio(self):
        self.assertEqual(deserializar(""), ("", {}))

    def test_texto_roto_no_revienta(self):
        self.assertEqual(deserializar("esto no es json"), ("", {}))


class TestFichas(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.usuarios.registrar("ana@correo.com", "miClaveSegura1", "Ana")
        self.fichas = FichasCobro(self.almacen, clave=bytes(range(32)))

    def tearDown(self):
        self.almacen.cerrar()

    def test_guardar_y_leer(self):
        self.fichas.guardar("ana@correo.com", "paypal", {
            "titular": "Ana Pérez", "correo": "ana@correo.com"})
        ficha = self.fichas.de("ana@correo.com")
        self.assertTrue(ficha.configurada)
        self.assertEqual(ficha.metodo, "paypal")
        self.assertEqual(ficha.campos["correo"], "ana@correo.com")

    def test_los_datos_se_guardan_cifrados(self):
        self.fichas.guardar("ana@correo.com", "cripto", {
            "titular": "Ana Pérez", "red": "TRC-20 (Tron)",
            "direccion": "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"})
        fila = self.almacen.usuario("ana@correo.com")
        crudo = fila["datos_cobro"]
        # La dirección NO puede aparecer en claro en la base de datos.
        self.assertNotIn("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", crudo)
        self.assertNotIn("Ana", crudo)
        # Y lo que se guardó sí se puede descifrar con la clave.
        self.assertIn("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", descifrar(crudo, bytes(range(32))))

    def test_sin_ficha_devuelve_vacia(self):
        ficha = self.fichas.de("ana@correo.com")
        self.assertFalse(ficha.configurada)
        self.assertEqual(ficha.metodo, "")

    def test_jugador_inexistente_no_se_puede_guardar(self):
        with self.assertRaises(ErrorDeDatosCobro):
            self.fichas.guardar("nadie@correo.com", "paypal",
                                {"titular": "X", "correo": "x@correo.com"})

    def test_otra_clave_no_puede_leer(self):
        self.fichas.guardar("ana@correo.com", "paypal",
                            {"titular": "Ana", "correo": "ana@correo.com"})
        otra = FichasCobro(self.almacen, clave=bytes([7] * 32))
        with self.assertRaises(ErrorDeFicha):
            otra.de("ana@correo.com")

    def test_de_seguro_no_revienta_con_clave_mala(self):
        self.fichas.guardar("ana@correo.com", "paypal",
                            {"titular": "Ana", "correo": "ana@correo.com"})
        otra = FichasCobro(self.almacen, clave=bytes([7] * 32))
        ficha = otra.de_seguro("ana@correo.com")
        self.assertFalse(ficha.configurada)

    def test_borrar(self):
        self.fichas.guardar("ana@correo.com", "paypal",
                            {"titular": "Ana", "correo": "ana@correo.com"})
        self.fichas.borrar("ana@correo.com")
        self.assertFalse(self.fichas.de("ana@correo.com").configurada)

    def test_clave_se_genera_sola_sin_entorno(self):
        # Sin clave pasada ni variable de entorno, se genera y se guarda en meta,
        # y sobrevive a un servicio nuevo sobre la misma base de datos.
        fichas = FichasCobro(self.almacen)
        fichas.guardar("ana@correo.com", "paypal",
                       {"titular": "Ana", "correo": "ana@correo.com"})
        otra_instancia = FichasCobro(self.almacen)
        self.assertEqual(otra_instancia.de("ana@correo.com").campos["correo"], "ana@correo.com")


class TestResumen(unittest.TestCase):
    def test_resumen_oculta_el_dato_completo(self):
        ficha = FichaCobro(correo="ana@correo.com", metodo="cripto",
                           campos={"titular": "Ana", "red": "TRC-20",
                                   "direccion": "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"})
        resumen = resumen_publico(ficha)
        self.assertIn("Ana", resumen)
        self.assertIn("LSE", resumen)          # se ven los últimos caracteres
        self.assertNotIn("TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", resumen)  # pero no entera

    def test_resumen_de_ficha_vacia(self):
        self.assertEqual(resumen_publico(FichaCobro(correo="x", metodo="", campos={})), "")


class TestSalaConPais(unittest.TestCase):
    """Opción A: cada sala nace con un país, y su precio vive en la moneda base."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.usuarios.registrar("ana@correo.com", "miClaveSegura1", "Ana")
        self.salas = Salas(self.almacen, usuarios=self.usuarios)

    def tearDown(self):
        self.almacen.cerrar()

    def test_las_salas_de_la_casa_nacen_en_venezuela(self):
        for s in self.salas.de_la_casa():
            self.assertEqual(s.pais, "VE")

    def test_una_sala_de_jugador_nace_con_el_pais_indicado(self):
        sala = self.salas.crear("ana@correo.com", "Mi sala", "normal", "10,00", pais="CO")
        self.assertEqual(sala.pais, "CO")

    def test_el_precio_de_la_sala_se_guarda_tal_cual(self):
        # Sin conversión: 10 dólares son 1.000 céntimos, mire quien mire.
        sala = self.salas.crear("ana@correo.com", "Mi sala", "normal", "10,00", pais="CO")
        self.assertEqual(sala.precio_carton, 1_000)
        self.assertEqual(sala.precio_nativo_texto, "$ 10,00")

    def test_un_pais_desconocido_cae_en_el_de_por_defecto(self):
        sala = self.salas.crear("ana@correo.com", "Mi sala", "normal", "10,00", pais="XX")
        self.assertEqual(sala.pais, "VE")

    def test_la_sala_guarda_su_pais_al_releerla(self):
        creada = self.salas.crear("ana@correo.com", "Mi sala", "normal", "10,00", pais="CL")
        otra = Salas(self.almacen, usuarios=self.usuarios).de(creada.id)
        self.assertEqual(otra.pais, "CL")

    def test_el_precio_se_muestra_igual_para_todos(self):
        from nucleo import paises

        sala = self.salas.de("sala-zulia")  # $ 10,00 de cartón
        paises.usar_pais("US")
        try:
            self.assertEqual(sala.precio_texto, "$ 10,00")
        finally:
            paises.usar_pais("VE")
        self.assertEqual(sala.precio_texto, "$ 10,00")


if __name__ == "__main__":
    unittest.main()
