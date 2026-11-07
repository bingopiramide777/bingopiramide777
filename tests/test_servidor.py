"""Pruebas del servidor: se arranca de verdad y se juega por HTTP.

Nada de simulacros: se levanta el servidor en un puerto libre, se registra un
usuario, se recarga, se compra cartón y se sacan bolas. Si esto pasa, la web
funciona.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from web.servidor import crear_servidor


class ServidorTest(unittest.TestCase):
    """Cada prueba levanta su propio servidor: así una partida en juego en una
    prueba no deja sin cartones a la siguiente."""

    def setUp(self):
        self.servidor = crear_servidor(host="127.0.0.1", puerto=0)
        self.puerto = self.servidor.server_address[1]
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.hilo.start()

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.hilo.join(timeout=5)

    # -- ayuda --

    def url(self, ruta):
        return f"http://127.0.0.1:{self.puerto}{ruta}"

    def pedir(self, ruta, datos=None, token=None, metodo=None):
        cabeceras = {"Content-Type": "application/json"}
        if token:
            cabeceras["Authorization"] = "Bearer " + token
        cuerpo = json.dumps(datos).encode() if datos is not None else None
        peticion = urllib.request.Request(
            self.url(ruta), data=cuerpo, headers=cabeceras, method=metodo or ("POST" if cuerpo else "GET")
        )
        try:
            with urllib.request.urlopen(peticion, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def nuevo_usuario(self):
        import random

        correo = f"prueba{random.randint(1, 10**9)}@correo.com"
        estado, _ = self.pedir("/api/registro", {"correo": correo, "clave": "miClaveSegura1"})
        self.assertEqual(estado, 200)
        _, datos = self.pedir("/api/entrar", {"correo": correo, "clave": "miClaveSegura1"})
        return datos["token"]

    # -- pruebas --

    def test_salud(self):
        estado, datos = self.pedir("/api/salud")
        self.assertEqual(estado, 200)
        self.assertEqual(datos["estado"], "bien")

    def test_la_portada_se_sirve(self):
        with urllib.request.urlopen(self.url("/"), timeout=10) as r:
            html = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("Bingo Pirámide 777", html)

    def test_no_se_puede_salir_de_la_carpeta_web(self):
        estado, _ = self.pedir("/../servidor.py")
        self.assertIn(estado, (400, 404))

    def test_sin_token_no_hay_saldo(self):
        estado, datos = self.pedir("/api/saldo")
        self.assertEqual(estado, 401)
        self.assertIn("error", datos)

    def test_flujo_completo(self):
        token = self.nuevo_usuario()

        # 1. Recargar
        estado, datos = self.pedir("/api/recargar", {"importe": "100,00"}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(datos["saldo"], 10_000)

        # 2. Comprar cartón
        estado, datos_carton = self.pedir("/api/carton", {}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(datos_carton["precio"], 1_000)
        self.assertEqual(len(datos_carton["numeros"]), 5)
        self.assertEqual(datos_carton["saldo"], 9_000)

        # 3. Sacar una bola
        estado, datos_bola = self.pedir("/api/bola", {}, token)
        self.assertEqual(estado, 200)
        self.assertTrue(1 <= datos_bola["bola"] <= 75)

        # 4. Cantar bingo sin tener línea: debe rechazarse
        carton_id = datos_carton["carton"]
        estado, _ = self.pedir("/api/bingo", {"carton": carton_id}, token)
        self.assertEqual(estado, 400)

    def test_sin_saldo_no_se_compra_carton(self):
        token = self.nuevo_usuario()
        estado, datos = self.pedir("/api/carton", {}, token)
        self.assertEqual(estado, 400)
        self.assertIn("insuficiente", datos["error"].lower())

    def test_la_partida_es_publica(self):
        estado, datos = self.pedir("/api/partida")
        self.assertEqual(estado, 200)
        self.assertIn("bolas_sacadas", datos)
        self.assertIn("estado", datos)

    def test_recarga_invalida(self):
        token = self.nuevo_usuario()
        for malo in ("", "abc", "-5"):
            estado, datos = self.pedir("/api/recargar", {"importe": malo}, token)
            self.assertEqual(estado, 400, f"'{malo}' debería rechazarse")

    def test_entrar_con_clave_mala(self):
        correo = "otro@correo.com"
        self.pedir("/api/registro", {"correo": correo, "clave": "miClaveSegura1"})
        estado, _ = self.pedir("/api/entrar", {"correo": correo, "clave": "claveMala999"})
        self.assertEqual(estado, 401)

    def test_ruta_desconocida(self):
        estado, _ = self.pedir("/api/no-existe")
        self.assertEqual(estado, 404)


if __name__ == "__main__":
    unittest.main()
