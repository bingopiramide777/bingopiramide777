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
            validar("paypal", {})

    def test_falta_un_campo_obligatorio(self):
        with self.assertRaises(ErrorDeDatosCobro):
            validar("pago_movil", {"titular": "Ana"})

    def test_pago_movil_completo(self):
        campos = validar("pago_movil", {
            "titular": "Ana Pérez", "banco": "Banesco",
            "telefono": "0414-1234567", "cedula": "V-12345678"})
        self.assertEqual(campos["banco"], "Banesco")
        self.assertEqual(campos["telefono"], "0414-1234567")

    def test_mach_permite_rut_vacio(self):
        # El RUT de MACH es opcional: sin él la ficha sigue siendo válida.
        campos = validar("mach", {"titular": "Luis", "telefono": "912345678", "rut": ""})
        self.assertNotIn("rut", campos)

    def test_telefono_con_letras_se_rechaza(self):
        with self.assertRaises(ErrorDeDatosCobro):
            validar("nequi", {"titular": "Ana", "telefono": "no-es-un-numero"})

    def test_se_descartan_campos_que_no_aplican(self):
        campos = validar("cashapp", {"titular": "Ana", "cashtag": "$ana", "banco": "Banesco"})
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
        self.fichas.guardar("ana@correo.com", "pago_movil", {
            "titular": "Ana Pérez", "banco": "Banesco",
            "telefono": "0414-1234567", "cedula": "V-12345678"})
        ficha = self.fichas.de("ana@correo.com")
        self.assertTrue(ficha.configurada)
        self.assertEqual(ficha.metodo, "pago_movil")
        self.assertEqual(ficha.campos["telefono"], "0414-1234567")

    def test_los_datos_se_guardan_cifrados(self):
        self.fichas.guardar("ana@correo.com", "pago_movil", {
            "titular": "Ana Pérez", "banco": "Banesco",
            "telefono": "0414-1234567", "cedula": "V-12345678"})
        fila = self.almacen.usuario("ana@correo.com")
        crudo = fila["datos_cobro"]
        # El número de teléfono NO puede aparecer en claro en la base de datos.
        self.assertNotIn("0414-1234567", crudo)
        self.assertNotIn("Ana", crudo)
        # Y lo que se guardó sí se puede descifrar con la clave.
        self.assertIn("0414-1234567", descifrar(crudo, bytes(range(32))))

    def test_sin_ficha_devuelve_vacia(self):
        ficha = self.fichas.de("ana@correo.com")
        self.assertFalse(ficha.configurada)
        self.assertEqual(ficha.metodo, "")

    def test_jugador_inexistente_no_se_puede_guardar(self):
        with self.assertRaises(ErrorDeDatosCobro):
            self.fichas.guardar("nadie@correo.com", "nequi",
                                {"titular": "X", "telefono": "3001234567"})

    def test_otra_clave_no_puede_leer(self):
        self.fichas.guardar("ana@correo.com", "nequi",
                            {"titular": "Ana", "telefono": "3001234567"})
        otra = FichasCobro(self.almacen, clave=bytes([7] * 32))
        with self.assertRaises(ErrorDeFicha):
            otra.de("ana@correo.com")

    def test_de_seguro_no_revienta_con_clave_mala(self):
        self.fichas.guardar("ana@correo.com", "nequi",
                            {"titular": "Ana", "telefono": "3001234567"})
        otra = FichasCobro(self.almacen, clave=bytes([7] * 32))
        ficha = otra.de_seguro("ana@correo.com")
        self.assertFalse(ficha.configurada)

    def test_borrar(self):
        self.fichas.guardar("ana@correo.com", "nequi",
                            {"titular": "Ana", "telefono": "3001234567"})
        self.fichas.borrar("ana@correo.com")
        self.assertFalse(self.fichas.de("ana@correo.com").configurada)

    def test_clave_se_genera_sola_sin_entorno(self):
        # Sin clave pasada ni variable de entorno, se genera y se guarda en meta,
        # y sobrevive a un servicio nuevo sobre la misma base de datos.
        fichas = FichasCobro(self.almacen)
        fichas.guardar("ana@correo.com", "nequi",
                       {"titular": "Ana", "telefono": "3001234567"})
        otra_instancia = FichasCobro(self.almacen)
        self.assertEqual(otra_instancia.de("ana@correo.com").campos["telefono"], "3001234567")


class TestResumen(unittest.TestCase):
    def test_resumen_oculta_el_dato_completo(self):
        ficha = FichaCobro(correo="ana@correo.com", metodo="pago_movil",
                           campos={"titular": "Ana", "telefono": "0414-1234567"})
        resumen = resumen_publico(ficha)
        self.assertIn("Ana", resumen)
        self.assertIn("4567", resumen)          # se ven los últimos dígitos
        self.assertNotIn("0414-1234567", resumen)  # pero no el número entero

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
        # 1.000 pesos colombianos (tasa 0,01) son Bs 10: dentro del rango válido.
        sala = self.salas.crear("ana@correo.com", "Mi sala", "normal", "1000,00", pais="CO")
        self.assertEqual(sala.pais, "CO")

    def test_el_precio_de_la_sala_se_guarda_en_la_moneda_base(self):
        # En Colombia, 1.000 pesos (tasa 0,01) son 10 bolívares = 1.000 céntimos.
        sala = self.salas.crear("ana@correo.com", "Mi sala", "normal", "1000,00", pais="CO")
        self.assertEqual(sala.precio_carton, 1_000)
        self.assertEqual(sala.precio_nativo_texto, "$ 1.000,00")

    def test_un_pais_desconocido_cae_en_el_de_por_defecto(self):
        sala = self.salas.crear("ana@correo.com", "Mi sala", "normal", "10,00", pais="XX")
        self.assertEqual(sala.pais, "VE")

    def test_la_sala_guarda_su_pais_al_releerla(self):
        # 250 pesos chilenos (tasa 0,04) son Bs 10.
        creada = self.salas.crear("ana@correo.com", "Mi sala", "normal", "250,00", pais="CL")
        otra = Salas(self.almacen, usuarios=self.usuarios).de(creada.id)
        self.assertEqual(otra.pais, "CL")

    def test_el_precio_se_muestra_convertido_a_quien_mira(self):
        from nucleo import paises

        sala = self.salas.de("sala-zulia")  # Bs 2.000,00 de cartón
        paises.usar_pais("US")
        try:
            # Con tasa 40, Bs 2.000 son 50 dólares.
            self.assertEqual(sala.precio_texto, "$ 50,00")
        finally:
            paises.usar_pais("VE")
        self.assertEqual(sala.precio_texto, "Bs 2.000,00")


if __name__ == "__main__":
    unittest.main()
