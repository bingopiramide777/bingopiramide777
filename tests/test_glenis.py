"""Pruebas de Glenis IA: sus herramientas y que no se le escape el dinero."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from nucleo import Almacen, Monedero, Usuarios
from nucleo.depositos import Depositos, hoy
from nucleo.fichas import FichasCobro
from nucleo.glenis import ErrorDeGlenis, Glenis
from nucleo.glenis_herramientas import Herramientas
from nucleo.retiros import Retiros
from nucleo.salas import Salas


class FalsoJuego:
    """Un juego mínimo, con piezas de verdad, para probar las herramientas."""

    def __init__(self):
        import threading

        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.retiros = Retiros(self.almacen, self.monedero)
        self.depositos = Depositos(self.almacen, self.monedero)
        self.salas = Salas(self.almacen)
        self.fichas = FichasCobro(self.almacen)
        self.candado = threading.RLock()
        self.usuarios.registrar("ana@correo.com", "miClaveSegura1", "Ana")

    def resumen(self):
        todos = self.usuarios.usuarios()
        return {"usuarios": len(todos),
                "jugadores": sum(1 for u in todos if u.rol == "jugador"),
                "total_en_cuentas": sum(self.monedero.saldo(u.correo)
                                        for u in self.usuarios.usuarios()),
                "retiros_pendientes": len(self.retiros.pendientes()),
                "total_pendiente": self.retiros.total_pendiente(),
                "depositos_pendientes": len(self.depositos.pendientes()),
                "depositos_pendiente_centimos": self.depositos.total_pendiente(),
                "partidas": 0, "apostado": 0, "pagado": 0, "margen": 0}


class HerramientasTest(unittest.TestCase):
    def setUp(self):
        self.juego = FalsoJuego()
        self.h = Herramientas(self.juego)

    def tearDown(self):
        self.juego.almacen.cerrar()

    def test_esquemas_bien_formados(self):
        for esquema in self.h.esquemas():
            f = esquema["function"]
            self.assertTrue(f["name"] and f["description"])
            self.assertEqual(f["parameters"]["type"], "object")

    def test_los_parametros_opcionales_aceptan_null(self):
        """La IA manda null en lo opcional que no usa. Si el esquema lo rechaza,
        la llamada entera falla y la herramienta no llega a ejecutarse."""
        for esquema in self.h.esquemas():
            f = esquema["function"]
            props = f["parameters"]["properties"]
            req = f["parameters"]["required"]
            for clave, definicion in props.items():
                if clave in req:
                    continue
                tipo = definicion["type"]
                self.assertIsInstance(tipo, list,
                                      f"{f['name']}.{clave} debería aceptar null")
                self.assertIn("null", tipo, f"{f['name']}.{clave} debería aceptar null")

    def test_ganancias_tolera_correo_nulo(self):
        """Regresión: la IA pidió ganancias con correo=null y la validación la tumbó."""
        r = self.h.ejecutar("ganancias", {"correo": None})
        self.assertIn("ganancia_de_la_app", r)
        r2 = self.h.ejecutar("ganancias", {})
        self.assertIn("ganancia_de_la_app", r2)

    def test_resumen(self):
        r = self.h.ejecutar("resumen", {})
        self.assertEqual(r["jugadores"], 1)
        self.assertEqual(r["administradores"], 0)
        self.assertEqual(r["dinero_en_cuentas"], "Bs 0,00")
        self.assertEqual(r["depositos_pendientes"], 0)

    def test_buscar_jugador(self):
        r = self.h.ejecutar("buscar_jugador", {"correo": "ana@correo.com"})
        self.assertEqual(r["correo"], "ana@correo.com")
        self.assertEqual(r["saldo"], "Bs 0,00")

    def test_buscar_jugador_que_no_existe(self):
        r = self.h.ejecutar("buscar_jugador", {"correo": "nadie@correo.com"})
        self.assertIn("error", r)

    def test_herramienta_inventada(self):
        self.assertIn("error", self.h.ejecutar("hackear_la_nasa", {}))

    def test_argumentos_mal_dados_no_revientan(self):
        self.assertIn("error", self.h.ejecutar("buscar_jugador", {"correo_typo": "x"}))

    # -- lo que toca dinero --

    def test_acreditar_deposito_suma_el_dinero(self):
        d = self.juego.depositos.declarar("ana@correo.com", "100,00", "123456",
                                          "Banco de Venezuela", hoy())
        r = self.h.ejecutar("acreditar_deposito", {"id": d.id, "nota": "verificado"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 10_000)

    def test_no_acredita_dos_veces(self):
        d = self.juego.depositos.declarar("ana@correo.com", "100,00", "123456",
                                          "Banco de Venezuela", hoy())
        self.h.ejecutar("acreditar_deposito", {"id": d.id})
        r = self.h.ejecutar("acreditar_deposito", {"id": d.id})
        self.assertIn("error", r)
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 10_000)

    def test_ajustar_saldo_exige_motivo(self):
        r = self.h.ejecutar("ajustar_saldo", {"correo": "ana@correo.com",
                                              "importe": "50,00", "motivo": ""})
        self.assertIn("error", r)
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 0)

    def test_ajustar_saldo_con_motivo(self):
        r = self.h.ejecutar("ajustar_saldo", {"correo": "ana@correo.com", "importe": "50,00",
                                              "motivo": "bono de bienvenida"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 5_000)

    def test_restar_no_deja_el_saldo_en_negativo(self):
        r = self.h.ejecutar("ajustar_saldo", {"correo": "ana@correo.com", "importe": "50,00",
                                              "motivo": "corrección", "signo": "restar"})
        self.assertIn("error", r)
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 0)

    def test_declarar_ganador_no_paga_solo(self):
        r = self.h.ejecutar("declarar_ganador", {"correo": "ana@correo.com", "premio": "160,00"})
        self.assertTrue(r["ok"])
        # Avisa, pero NO ingresa el premio: eso lo paga la persona.
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 0)
        self.assertIn("administración", r["nota"])

    def test_anotar_pago_manual_no_mueve_el_saldo(self):
        r = self.h.ejecutar("anotar_pago_manual", {"correo": "ana@correo.com",
                                                   "importe": "160,00", "referencia": "777"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.juego.monedero.saldo("ana@correo.com"), 0)

    def test_quedan_anotadas_las_acciones(self):
        self.h.ejecutar("buscar_jugador", {"correo": "ana@correo.com"})
        self.h.ejecutar("resumen", {})
        nombres = [a["herramienta"] for a in self.h.registro]
        self.assertEqual(nombres, ["buscar_jugador", "resumen"])

    # -- cuentas de la administración (la casa) --

    def test_cuentas_admin_lista_los_cuatro_paises(self):
        r = self.h.ejecutar("cuentas_admin", {})
        self.assertEqual([c["pais"] for c in r["cuentas"]], ["VE", "CO", "CL", "US"])
        self.assertEqual(r["cuentas"][0]["nombre_pais"], "Venezuela")

    def test_cuentas_admin_filtra_por_pais(self):
        r = self.h.ejecutar("cuentas_admin", {"pais": "co"})
        self.assertEqual(len(r["cuentas"]), 1)
        self.assertEqual(r["cuentas"][0]["pais"], "CO")
        self.assertEqual(r["cuentas"][0]["moneda"], "COP")

    def test_cuentas_admin_pais_invalido(self):
        r = self.h.ejecutar("cuentas_admin", {"pais": "XX"})
        self.assertIn("error", r)

    def test_cuentas_admin_avisa_de_las_que_faltan(self):
        """Sin variables de entorno, las cuentas salen sin configurar y se avisa."""
        r = self.h.ejecutar("cuentas_admin", {})
        self.assertEqual(r["sin_configurar"], ["VE", "CO", "CL", "US"])
        self.assertIn("CASA", r["aviso"])

    def test_cuentas_admin_tolera_pais_nulo(self):
        """La IA manda null cuando no usa el filtro: no debe reventar."""
        r = self.h.ejecutar("cuentas_admin", {"pais": None})
        self.assertEqual(len(r["cuentas"]), 4)

    # -- el premio se paga por el instrumento que el ganador registró --

    def _partida_con_ganador(self, premio: int = 16_000) -> str:
        self.juego.almacen.guardar_partida({
            "id": "p-1", "sala": "", "patron": "linea", "precio_carton": 1_000,
            "estado": "terminada", "bolas": "1,2,3", "ganador": "ana@correo.com",
            "carton_ganador": 1, "premio": premio})
        return "p-1"

    def test_acreditacion_avisa_si_el_ganador_no_registro_como_cobrar(self):
        self._partida_con_ganador()
        r = self.h.ejecutar("datos_de_acreditacion", {"correo": "ana@correo.com"})
        fila = r["acreditaciones"][0]
        self.assertFalse(fila["instrumento_registrado"])
        self.assertIn("falta", fila)
        self.assertIn("perfil", fila["falta"])

    def test_acreditacion_muestra_el_instrumento_registrado(self):
        self._partida_con_ganador()
        self.juego.fichas.guardar("ana@correo.com", "pago_movil", {
            "titular": "Ana Pérez", "banco": "Banesco",
            "telefono": "04161234567", "cedula": "V-12345678"})
        r = self.h.ejecutar("datos_de_acreditacion", {"correo": "ana@correo.com"})
        fila = r["acreditaciones"][0]
        self.assertTrue(fila["instrumento_registrado"])
        self.assertEqual(fila["metodo_de_pago"], "pago_movil")
        self.assertEqual(fila["datos_de_pago"]["Teléfono"], "04161234567")

    def test_acreditacion_sin_partidas_no_revienta(self):
        r = self.h.ejecutar("datos_de_acreditacion", {})
        self.assertIn("aviso", r)


class GlenisTest(unittest.TestCase):
    def setUp(self):
        self.juego = FalsoJuego()
        self.h = Herramientas(self.juego)
        self.ejecutadas = []

        def ejecutor(nombre, argumentos):
            self.ejecutadas.append(nombre)
            return self.h.ejecutar(nombre, argumentos)

        self.glenis = Glenis(self.h.esquemas(), ejecutor, clave="clave-de-prueba")

    def tearDown(self):
        self.juego.almacen.cerrar()

    def _respuesta(self, mensaje):
        return {"choices": [{"message": mensaje}]}

    def test_sin_clave_avisa_claro(self):
        g = Glenis(self.h.esquemas(), lambda n, a: {}, clave="")
        self.assertFalse(g.configurada)
        with self.assertRaises(ErrorDeGlenis):
            g.conversar([{"role": "user", "content": "hola"}])

    def test_respuesta_simple_sin_herramientas(self):
        with patch.object(self.glenis, "_pedir", return_value=self._respuesta(
                {"content": "Hay 1 jugador."})):
            r = self.glenis.conversar([{"role": "user", "content": "¿cuántos jugadores?"}])
        self.assertEqual(r.texto, "Hay 1 jugador.")
        self.assertEqual(self.ejecutadas, [])

    def test_ejecuta_la_herramienta_que_pide_la_ia(self):
        pasos = [
            self._respuesta({"content": None, "tool_calls": [
                {"id": "1", "function": {"name": "resumen", "arguments": "{}"}}]}),
            self._respuesta({"content": "Hay 1 jugador y Bs 0,00."}),
        ]
        with patch.object(self.glenis, "_pedir", side_effect=pasos):
            r = self.glenis.conversar([{"role": "user", "content": "resumen"}])
        self.assertEqual(self.ejecutadas, ["resumen"])
        self.assertIn("1 jugador", r.texto)
        self.assertEqual(len(r.acciones), 1)

    def test_para_si_da_demasiadas_vueltas(self):
        bucle = self._respuesta({"content": None, "tool_calls": [
            {"id": "1", "function": {"name": "resumen", "arguments": "{}"}}]})
        with patch.object(self.glenis, "_pedir", return_value=bucle):
            r = self.glenis.conversar([{"role": "user", "content": "x"}])
        self.assertEqual(r.pasos, 6)
        self.assertIn("vueltas", r.texto)

    def test_argumentos_rotos_no_revientan(self):
        pasos = [
            self._respuesta({"content": None, "tool_calls": [
                {"id": "1", "function": {"name": "resumen", "arguments": "no es json"}}]}),
            self._respuesta({"content": "Listo."}),
        ]
        with patch.object(self.glenis, "_pedir", side_effect=pasos):
            r = self.glenis.conversar([{"role": "user", "content": "x"}])
        self.assertEqual(r.texto, "Listo.")

    def test_error_de_la_ia_se_explica(self):
        import urllib.error

        with patch.object(self.glenis, "_pedir",
                          side_effect=ErrorDeGlenis("La IA respondió con error 429.")):
            with self.assertRaises(ErrorDeGlenis):
                self.glenis.conversar([{"role": "user", "content": "x"}])


if __name__ == "__main__":
    unittest.main()
