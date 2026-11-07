"""Pruebas de Glenis IA: sus herramientas y que no se le escape el dinero."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from nucleo import Almacen, Monedero, Usuarios
from nucleo.depositos import Depositos, hoy
from nucleo.glenis import ErrorDeGlenis, Glenis
from nucleo.glenis_herramientas import Herramientas
from nucleo.retiros import Retiros


class FalsoJuego:
    """Un juego mínimo, con piezas de verdad, para probar las herramientas."""

    def __init__(self):
        import threading

        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.retiros = Retiros(self.almacen, self.monedero)
        self.depositos = Depositos(self.almacen, self.monedero)
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
