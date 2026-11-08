"""Pruebas del servidor: se arranca de verdad y se juega por HTTP.

Nada de simulacros: cada prueba levanta su propio servidor con su base de datos.
Si esto pasa, la web funciona.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from nucleo import Almacen
from web.servidor import Juego, crear_servidor

ADMIN = "bingopiramide777@gmail.com"
CLAVE_ADMIN = "ClaveAdmin777"


class ServidorTest(unittest.TestCase):
    def setUp(self):
        self.ruta = os.path.join(tempfile.mkdtemp(), "prueba.db")
        self.almacen = Almacen(self.ruta)
        self.juego = Juego(almacen=self.almacen, correo_admin=ADMIN, clave_admin=CLAVE_ADMIN)
        self.servidor = crear_servidor(host="127.0.0.1", puerto=0, juego=self.juego)
        self.puerto = self.servidor.server_address[1]
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.hilo.start()

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.hilo.join(timeout=5)
        self.almacen.cerrar()

    # -- ayuda --

    def pedir(self, ruta, datos=None, token=None, cabeceras_extra=None):
        cabeceras = {"Content-Type": "application/json"}
        if token:
            cabeceras["Authorization"] = "Bearer " + token
        if cabeceras_extra:
            cabeceras.update(cabeceras_extra)
        cuerpo = json.dumps(datos).encode() if datos is not None else None
        peticion = urllib.request.Request(
            f"http://127.0.0.1:{self.puerto}{ruta}", data=cuerpo, headers=cabeceras,
            method="POST" if cuerpo else "GET")
        try:
            with urllib.request.urlopen(peticion, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def usuario(self, correo, clave="miClaveSegura1", recarga=None):
        self.pedir("/api/registro", {"correo": correo, "clave": clave})
        _, d = self.pedir("/api/entrar", {"correo": correo, "clave": clave})
        token = d["token"]
        if recarga:
            # El saldo se ingresa como lo hace la administración: el jugador ya no
            # puede recargarse solo (eso era un agujero de dinero gratis).
            self.pedir("/api/recargar", {"correo": correo, "importe": recarga}, self.admin())
        return token

    def admin(self):
        _, d = self.pedir("/api/entrar", {"correo": ADMIN, "clave": CLAVE_ADMIN})
        return d["token"]

    # -- pruebas básicas --

    def test_salud(self):
        estado, datos = self.pedir("/api/salud")
        self.assertEqual(estado, 200)
        self.assertEqual(datos["estado"], "bien")

    def test_la_portada_se_sirve(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.puerto}/", timeout=10) as r:
            html = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("BINGO", html)
        self.assertIn("Somos la pepa del queso", html)

    def test_el_panel_de_admin_se_sirve(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.puerto}/admin", timeout=10) as r:
            html = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("administración", html.lower())

    def test_no_se_puede_salir_de_la_carpeta_web(self):
        estado, _ = self.pedir("/../servidor.py")
        self.assertIn(estado, (400, 404))

    def test_sin_token_no_hay_saldo(self):
        estado, datos = self.pedir("/api/saldo")
        self.assertEqual(estado, 401)

    # -- juego --

    def test_flujo_completo_de_juego(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        # Se juega en la sala Lara (Bs 1.000 el cartón).
        _, c = self.pedir("/api/carton", {"sala": "sala-lara"}, token)
        self.assertEqual(c["precio"], 100_000)
        self.assertEqual(c["saldo"], 400_000)
        estado, b = self.pedir("/api/bola", {}, token)
        self.assertEqual(estado, 200)
        self.assertTrue(1 <= b["bola"] <= 75)
        estado, _ = self.pedir("/api/bingo", {"carton": c["carton"]}, token)
        self.assertEqual(estado, 400)  # sin línea completa, se rechaza

    def test_sin_saldo_no_se_compra_carton(self):
        token = self.usuario("ana@correo.com")
        estado, datos = self.pedir("/api/carton", {}, token)
        self.assertEqual(estado, 400)

    def test_comprar_varios_cartones_de_una_vez(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        estado, r = self.pedir("/api/carton", {"sala": "sala-lara", "cantidad": 3}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["cantidad"], 3)
        self.assertEqual(len(r["cartones"]), 3)
        # Tres cartones de Bs 1.000: cobra 3.000 y el saldo baja en consecuencia.
        self.assertEqual(r["saldo"], 200_000)
        ids = {c["carton"] for c in r["cartones"]}
        self.assertEqual(len(ids), 3)  # cada uno con su id

    def test_la_cantidad_se_limita_a_diez(self):
        token = self.usuario("ana@correo.com", recarga="99999,00")
        _, r = self.pedir("/api/carton", {"sala": "sala-lara", "cantidad": 999}, token)
        self.assertEqual(r["cantidad"], 10)

    def test_cantidad_invalida_compra_uno(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        _, r = self.pedir("/api/carton", {"sala": "sala-lara", "cantidad": "muchos"}, token)
        self.assertEqual(r["cantidad"], 1)

    def test_la_partida_es_publica(self):
        estado, datos = self.pedir("/api/partida")
        self.assertEqual(estado, 200)
        self.assertIn("bolas_sacadas", datos)

    def test_recarga_invalida(self):
        token = self.usuario("ana@correo.com")
        for malo in ("", "abc", "-5"):
            estado, _ = self.pedir("/api/recargar", {"correo": "ana@correo.com", "importe": malo},
                                   self.admin())
            self.assertEqual(estado, 400, f"'{malo}' debería rechazarse")

    def test_un_jugador_no_puede_ingresarse_saldo(self):
        """El agujero del dinero gratis: un jugador no puede recargarse solo."""
        token = self.usuario("ana@correo.com")
        estado, datos = self.pedir("/api/recargar", {"importe": "50000,00"}, token)
        self.assertEqual(estado, 403)
        _, s = self.pedir("/api/saldo", token=token)
        self.assertEqual(s["saldo"], 0, "el saldo no puede haber cambiado")

    # -- persistencia --

    def test_el_saldo_sobrevive_al_reinicio(self):
        token = self.usuario("ana@correo.com", recarga="250,00")
        # Cerramos el servidor y levantamos otro sobre la misma base de datos.
        self.servidor.shutdown(); self.servidor.server_close(); self.hilo.join(timeout=5)
        self.almacen.cerrar()

        self.almacen = Almacen(self.ruta)
        self.juego = Juego(almacen=self.almacen, correo_admin=ADMIN, clave_admin=CLAVE_ADMIN)
        self.servidor = crear_servidor(host="127.0.0.1", puerto=0, juego=self.juego)
        self.puerto = self.servidor.server_address[1]
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.hilo.start()

        _, d = self.pedir("/api/entrar", {"correo": "ana@correo.com", "clave": "miClaveSegura1"})
        _, s = self.pedir("/api/saldo", token=d["token"])
        self.assertEqual(s["saldo"], 25_000)

    # -- retiros --

    def test_flujo_de_retiro_completo(self):
        token = self.usuario("ana@correo.com", recarga="1000,00")
        _, r = self.pedir("/api/retiro",
                          {"importe": "500,00", "metodo": "transferencia",
                           "detalles": "Banco de Venezuela, cuenta 0102..."}, token)
        self.assertEqual(r["retiro"]["estado"], "pendiente")
        _, s = self.pedir("/api/saldo", token=token)
        self.assertEqual(s["saldo"], 50_000)   # se descontó al pedir

        # El administrador lo ve y lo paga.
        at = self.admin()
        _, pend = self.pedir("/api/admin/retiros?estado=pendiente", token=at)
        self.assertEqual(len(pend["retiros"]), 1)
        rid = pend["retiros"][0]["id"]
        estado, res = self.pedir("/api/admin/retiro", {"id": rid, "accion": "pagar"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(res["retiro"]["estado"], "pagado")

        # Pagar no devuelve el saldo.
        _, s = self.pedir("/api/saldo", token=token)
        self.assertEqual(s["saldo"], 50_000)

    def test_rechazar_retiro_devuelve_el_saldo(self):
        token = self.usuario("ana@correo.com", recarga="1000,00")
        _, r = self.pedir("/api/retiro", {"importe": "500,00", "metodo": "pago_movil",
                                          "detalles": "0414-1234567"}, token)
        at = self.admin()
        self.pedir("/api/admin/retiro", {"id": r["retiro"]["id"], "accion": "rechazar", "nota": "mal"}, at)
        _, s = self.pedir("/api/saldo", token=token)
        self.assertEqual(s["saldo"], 100_000)

    def test_retiro_sin_saldo(self):
        token = self.usuario("ana@correo.com")
        estado, _ = self.pedir("/api/retiro", {"importe": "500,00", "metodo": "transferencia",
                                               "detalles": "Banco X 123456"}, token)
        self.assertEqual(estado, 400)

    # -- recuperación de cuenta --

    def test_recuperacion_con_pregunta_secreta(self):
        from nucleo.usuarios import PREGUNTAS
        self.pedir("/api/registro", {"correo": "ana@correo.com", "clave": "miClaveSegura1",
                                     "pregunta": PREGUNTAS[0], "respuesta": "Firulais"})
        _, p = self.pedir("/api/recuperar/pregunta", {"correo": "ana@correo.com"})
        self.assertEqual(p["pregunta"], PREGUNTAS[0])
        estado, _ = self.pedir("/api/recuperar/pregunta/cambiar",
                               {"correo": "ana@correo.com", "respuesta": "firulais",
                                "clave": "ClaveNueva123"})
        self.assertEqual(estado, 200)
        estado, _ = self.pedir("/api/entrar", {"correo": "ana@correo.com", "clave": "ClaveNueva123"})
        self.assertEqual(estado, 200)

    def test_recuperacion_con_codigo(self):
        self.usuario("ana@correo.com")
        estado, res = self.pedir("/api/recuperar/codigo", {"correo": "ana@correo.com"})
        self.assertEqual(estado, 200)
        # Sin correo configurado, no se envía, pero tampoco se miente.
        self.assertFalse(res["enviado"])
        self.assertIn("Si ese correo", res["mensaje"])
        # El código sí se ha generado en la base: se puede usar.
        codigo = self.juego.almacen.codigo_pendiente("ana@correo.com")
        self.assertIsNotNone(codigo)

    def test_pedir_codigo_de_correo_inexistente_responde_igual(self):
        _, a = self.pedir("/api/recuperar/codigo", {"correo": "nadie@correo.com"})
        _, b = self.pedir("/api/recuperar/codigo", {"correo": "ana@correo.com"})
        self.assertEqual(a["mensaje"], b["mensaje"])
        self.assertEqual(a["enviado"], b["enviado"])

    def test_cambiar_la_clave_cierra_las_sesiones(self):
        token = self.usuario("ana@correo.com")
        self.pedir("/api/registro", {"correo": "ana@correo.com", "clave": "x"})  # ya existe
        # La sesión abierta funciona.
        self.assertEqual(self.pedir("/api/saldo", token=token)[0], 200)
        with self.juego.candado:
            self.juego.usuarios.restablecer_por_admin("ana@correo.com", "ClaveNueva123")
        # Y ahora queda cerrada.
        self.assertEqual(self.pedir("/api/saldo", token=token)[0], 401)

    def test_el_admin_restablece_la_clave_de_un_jugador(self):
        self.usuario("ana@correo.com")
        at = self.admin()
        estado, res = self.pedir("/api/admin/restablecer", {"correo": "ana@correo.com"}, at)
        self.assertEqual(estado, 200)
        self.assertTrue(res["clave"])
        # La clave temporal funciona.
        estado, _ = self.pedir("/api/entrar", {"correo": "ana@correo.com", "clave": res["clave"]})
        self.assertEqual(estado, 200)

    def test_solo_el_admin_restablece_claves(self):
        token = self.usuario("ana@correo.com")
        estado, _ = self.pedir("/api/admin/restablecer", {"correo": "ana@correo.com"}, token)
        self.assertEqual(estado, 403)

    # -- salas --

    def test_vienen_las_salas_de_la_casa(self):
        estado, r = self.pedir("/api/salas")
        self.assertEqual(estado, 200)
        self.assertEqual([s["nombre"] for s in r["salas"]],
                         ["Zulia", "Lara", "Carabobo", "Mérida", "Táchira", "Nueva Esparta",
                          "Ganar Dinero Desde Casa con BingoPiramide777",
                          "Sala de Eventos Lago de Maracaibo"])

    def test_la_sala_de_jugar_desde_casa_viene_configurada(self):
        _, r = self.pedir("/api/salas")
        sala = next(s for s in r["salas"] if s["id"] == "sala-ganar-desde-casa")
        self.assertEqual(sala["modo"], "carton_lleno")
        self.assertEqual(sala["max_cartones"], 6)
        self.assertEqual(sala["precio_texto"], "Bs 50,00")

    def test_no_se_pueden_comprar_mas_de_seis_cartones_en_la_sala_de_casa(self):
        """El tope por jugador es lo que impide acaparar el bote."""
        token = self.usuario("ana@correo.com", recarga="5000,00")
        # Seis cartones: entran.
        estado, r = self.pedir("/api/carton",
                               {"sala": "sala-ganar-desde-casa", "cantidad": 6}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["cantidad"], 6)
        # El séptimo se rechaza y no cobra nada.
        estado, err = self.pedir("/api/carton", {"sala": "sala-ganar-desde-casa"}, token)
        self.assertEqual(estado, 400)
        self.assertIn("6 cartones", err["error"])
        # Se cobraron los seis cartones, ni uno más.
        _, saldo = self.pedir("/api/saldo", token=token)
        self.assertEqual(saldo["saldo"], 500_000 - 6 * 5_000)

    def test_pasarse_del_tope_no_deja_media_compra_hecha(self):
        """Si pide 5 y solo le caben 2, no se le cobra nada."""
        token = self.usuario("ana@correo.com", recarga="5000,00")
        self.pedir("/api/carton", {"sala": "sala-ganar-desde-casa", "cantidad": 4}, token)
        estado, err = self.pedir("/api/carton",
                                 {"sala": "sala-ganar-desde-casa", "cantidad": 4}, token)
        self.assertEqual(estado, 400)
        _, saldo = self.pedir("/api/saldo", token=token)
        self.assertEqual(saldo["saldo"], 500_000 - 4 * 5_000)

    def test_un_jugador_crea_su_sala(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/sala/crear", {
            "nombre": "La de Ana", "modo": "normal", "precio": "25,00", "publica": True}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["precio_texto"], "Bs 25,00")
        self.assertEqual(r["sala"]["dueno"], "ana@correo.com")
        self.assertIn("10%", r["mensaje"])

    def test_crear_sala_necesita_entrar(self):
        estado, _ = self.pedir("/api/sala/crear",
                               {"nombre": "X", "modo": "normal", "precio": "10,00"})
        self.assertEqual(estado, 401)

    def test_la_sala_aparece_en_la_lista_publica(self):
        token = self.usuario("ana@correo.com")
        self.pedir("/api/sala/crear",
                   {"nombre": "La de Ana", "modo": "normal", "precio": "10,00"}, token)
        _, r = self.pedir("/api/salas")
        self.assertIn("La de Ana", [s["nombre"] for s in r["salas"]])

    def test_la_sala_privada_no_sale_en_la_lista_pero_si_por_su_enlace(self):
        """El enlace de una sala privada es exclusivo: no se lista, pero entra."""
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/sala/crear",
                          {"nombre": "La de Ana", "modo": "normal",
                           "precio": "10,00", "publica": False}, token)
        sala_id = r["sala"]["id"]
        self.assertFalse(r["sala"]["publica"])
        # No aparece en el listado público...
        _, listado = self.pedir("/api/salas")
        self.assertNotIn(sala_id, [s["id"] for s in listado["salas"]])
        # ...pero quien tiene el enlace (el id) entra sin problema.
        estado, entra = self.pedir("/api/sala/entrar", {"sala": sala_id}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(entra["partida"]["sala_nombre"], "La de Ana")

    def test_entrar_a_una_sala_incluye_el_tope_de_cartones(self):
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/sala/entrar", {"sala": "sala-ganar-desde-casa"}, token)
        self.assertEqual(r["partida"]["max_cartones"], 6)
        _, r2 = self.pedir("/api/sala/entrar", {"sala": "sala-zulia"}, token)
        self.assertEqual(r2["partida"]["max_cartones"], 0)

    def test_mis_salas_trae_las_ganancias(self):
        token = self.usuario("ana@correo.com")
        self.pedir("/api/sala/crear",
                   {"nombre": "La de Ana", "modo": "normal", "precio": "10,00"}, token)
        estado, r = self.pedir("/api/mis-salas", token=token)
        self.assertEqual(estado, 200)
        self.assertEqual(len(r["salas"]), 1)
        self.assertEqual(r["ganancias"]["anfitrion"], 0)
        self.assertEqual(r["ganancias"]["anfitrion_texto"], "Bs 0,00")

    def test_el_jugador_juega_en_la_sala_que_elige(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        _, r = self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        self.assertEqual(r["precio"], 200_000)   # Zulia: Bs 2.000

    def test_entrar_a_una_sala_da_su_modo_y_reparto(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/sala/entrar", {"sala": "sala-carabobo"}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["partida"]["modo"], "carton_lleno")
        self.assertEqual(r["partida"]["sala_nombre"], "Carabobo")

    def test_solo_el_admin_ve_las_salas_del_panel(self):
        token = self.usuario("ana@correo.com")
        self.assertEqual(self.pedir("/api/admin/salas", token=token)[0], 403)
        at = self.admin()
        estado, r = self.pedir("/api/admin/salas", token=at)
        self.assertEqual(estado, 200)
        self.assertIn("economia", r)

    # -- sala de eventos --

    def test_la_sala_de_eventos_se_ve_sin_entrar(self):
        estado, r = self.pedir("/api/evento")
        self.assertEqual(estado, 200)
        self.assertEqual(r["nombre"], "Sala de Eventos Lago de Maracaibo")
        self.assertEqual(r["aforo"], 50)
        self.assertEqual([p["pct"] for p in r["premios"]], [60, 15, 5])

    def test_solo_el_admin_configura_el_evento(self):
        token = self.usuario("ana@correo.com")
        estado, _ = self.pedir("/api/admin/evento", {"precio": "100,00"}, token)
        self.assertEqual(estado, 403)

    def test_el_admin_configura_precio_aforo_y_premios(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/evento",
                               {"precio": "100,00", "aforo": 2, "premios_pct": "70,20,10"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["evento"]["precio_texto"], "Bs 100,00")
        self.assertEqual(r["evento"]["aforo"], 2)
        self.assertEqual([p["pct"] for p in r["evento"]["premios"]], [70, 20, 10])

    def test_los_premios_del_evento_se_reparten_por_porcentaje(self):
        at = self.admin()
        self.pedir("/api/admin/evento",
                   {"precio": "100,00", "aforo": 50, "premios_pct": "60,15,5"}, at)
        tokens = [self.usuario(f"j{i}@correo.com", recarga="1000,00") for i in range(3)]
        for t in tokens:
            self.pedir("/api/carton", {"sala": "sala-evento-lago"}, t)
        estado, r = self.pedir("/api/evento")
        # 3 cartones x Bs 100 = Bs 300 de bote.
        self.assertEqual(r["bote"], 30_000)
        self.assertEqual([p["premio"] for p in r["premios"]], [18_000, 4_500, 1_500])

    def test_el_aforo_del_evento_limita_los_jugadores(self):
        at = self.admin()
        self.pedir("/api/admin/evento", {"aforo": 2}, at)
        t1 = self.usuario("j1@correo.com", recarga="1000,00")
        t2 = self.usuario("j2@correo.com", recarga="1000,00")
        t3 = self.usuario("j3@correo.com", recarga="1000,00")
        self.assertEqual(self.pedir("/api/carton", {"sala": "sala-evento-lago"}, t1)[0], 200)
        self.assertEqual(self.pedir("/api/carton", {"sala": "sala-evento-lago"}, t2)[0], 200)
        # El tercero no cabe: el aforo es de 2 jugadores.
        estado, datos = self.pedir("/api/carton", {"sala": "sala-evento-lago"}, t3)
        self.assertEqual(estado, 400)
        self.assertIn("llena", datos["error"].lower())

    def test_quien_ya_esta_dentro_puede_comprar_mas_cartones(self):
        at = self.admin()
        self.pedir("/api/admin/evento", {"aforo": 1}, at)
        t1 = self.usuario("j1@correo.com", recarga="1000,00")
        self.assertEqual(self.pedir("/api/carton", {"sala": "sala-evento-lago"}, t1)[0], 200)
        self.assertEqual(self.pedir("/api/carton", {"sala": "sala-evento-lago"}, t1)[0], 200)

    # -- ver una sala por dentro (solo admin) --

    def test_solo_el_admin_ve_el_interior_de_una_sala(self):
        token = self.usuario("ana@correo.com")
        estado, _ = self.pedir("/api/admin/sala?sala=sala-zulia", token=token)
        self.assertEqual(estado, 403)

    def test_el_admin_ve_los_jugadores_de_una_sala(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala?sala=sala-zulia", token=at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["nombre"], "Zulia")
        self.assertEqual([j["correo"] for j in r["jugadores"]], ["ana@correo.com"])
        self.assertEqual(r["jugadores"][0]["cartones"], 1)

    def test_la_vista_de_sala_trae_los_cartones_con_sus_marcas(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        at = self.admin()
        _, r = self.pedir("/api/admin/sala?sala=sala-zulia", token=at)
        carton = r["jugadores"][0]["detalle"][0]
        self.assertEqual(len(carton["numeros"]), 5)
        # El centro (2-2) siempre va marcado: es el comodín del cartón.
        self.assertIn("2-2", carton["marcados"])

    def test_la_vista_de_sala_sin_partida_no_revienta(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala?sala=sala-miranda", token=at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["jugadores"], [])

    def test_la_vista_de_sala_pide_el_nombre_de_la_sala(self):
        at = self.admin()
        estado, _ = self.pedir("/api/admin/sala", token=at)
        self.assertEqual(estado, 400)

    def test_la_vista_de_una_sala_inexistente_da_error(self):
        at = self.admin()
        estado, _ = self.pedir("/api/admin/sala?sala=sala-fantasma", token=at)
        self.assertEqual(estado, 400)

    def test_ir_y_volver_entre_salas_no_rompe_la_partida(self):
        """Cambiar de sala y volver no debe intentar reabrir una partida viva.

        Rehidratarla desde la base cuando el objeto sigue en memoria lanzaba
        "La partida X ya existe" y dejaba la mesa sin cargar.
        """
        token = self.usuario("ana@correo.com", recarga="5000,00")
        self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        self.pedir("/api/carton", {"sala": "sala-lara"}, token)
        self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        estado, r = self.pedir("/api/partida")
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"], "sala-zulia")
        self.assertEqual(r["jugadores"], 1)

    def test_el_admin_cierra_una_sala_de_jugador(self):
        token = self.usuario("ana@correo.com")
        _, s = self.pedir("/api/sala/crear",
                          {"nombre": "La de Ana", "modo": "normal", "precio": "10,00"}, token)
        at = self.admin()
        self.assertEqual(self.pedir("/api/sala/cerrar", {"sala": s["sala"]["id"]}, at)[0], 200)
        _, r = self.pedir("/api/admin/salas", token=at)
        cerrada = [x for x in r["salas"] if x["id"] == s["sala"]["id"]][0]
        self.assertFalse(cerrada["activa"])

    # -- depósitos y Glenis --

    def test_el_jugador_declara_un_deposito(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/deposito", {
            "importe": "150,00", "referencia": "123456789", "banco": "Banco de Venezuela",
            "dia": time.strftime("%Y-%m-%d"), "metodo": "pago_movil"}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["deposito"]["estado"], "pendiente")
        # Y todavía no hay dinero.
        self.assertEqual(self.pedir("/api/saldo", token=token)[1]["saldo"], 0)

    def test_declarar_deposito_necesita_entrar(self):
        estado, _ = self.pedir("/api/deposito", {"importe": "100,00", "referencia": "123456",
                                                 "banco": "Banco de Venezuela",
                                                 "dia": time.strftime("%Y-%m-%d")})
        self.assertEqual(estado, 401)

    def test_la_misma_referencia_se_rechaza(self):
        token = self.usuario("ana@correo.com")
        hoy = time.strftime("%Y-%m-%d")
        base = {"importe": "100,00", "referencia": "555555", "banco": "Banesco", "dia": hoy}
        self.assertEqual(self.pedir("/api/deposito", base, token)[0], 200)
        self.assertEqual(self.pedir("/api/deposito", base, token)[0], 400)

    def test_el_admin_acredita_el_deposito(self):
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/deposito", {"importe": "150,00", "referencia": "999888",
                                            "banco": "Banesco",
                                            "dia": time.strftime("%Y-%m-%d")}, token)
        at = self.admin()
        estado, res = self.pedir("/api/admin/deposito",
                                 {"id": r["deposito"]["id"], "accion": "acreditar"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(res["deposito"]["estado"], "acreditado")
        self.assertEqual(self.pedir("/api/saldo", token=token)[1]["saldo"], 15_000)

    def test_solo_el_admin_acredita(self):
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/deposito", {"importe": "100,00", "referencia": "777777",
                                            "banco": "Banesco",
                                            "dia": time.strftime("%Y-%m-%d")}, token)
        estado, _ = self.pedir("/api/admin/deposito",
                               {"id": r["deposito"]["id"], "accion": "acreditar"}, token)
        self.assertEqual(estado, 403)
        self.assertEqual(self.pedir("/api/saldo", token=token)[1]["saldo"], 0)

    def test_el_jugador_ve_sus_depositos(self):
        token = self.usuario("ana@correo.com")
        self.pedir("/api/deposito", {"importe": "100,00", "referencia": "444444",
                                     "banco": "Banesco", "dia": time.strftime("%Y-%m-%d")}, token)
        estado, r = self.pedir("/api/depositos", token=token)
        self.assertEqual(estado, 200)
        self.assertEqual(len(r["depositos"]), 1)

    def test_glenis_solo_para_admin(self):
        token = self.usuario("ana@correo.com")
        self.assertEqual(self.pedir("/api/admin/glenis", token=token)[0], 403)
        self.assertEqual(self.pedir("/api/admin/glenis",
                                    {"mensaje": "hola"}, token)[0], 403)

    def test_glenis_avisa_si_no_tiene_clave(self):
        """Sin clave configurada, el panel lo dice en vez de aparentar que funciona."""
        at = self.admin()
        estado, r = self.pedir("/api/admin/glenis", token=at)   # GET
        self.assertEqual(estado, 200)
        self.assertFalse(r["configurada"])

    def test_glenis_no_inventa_si_no_hay_clave(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/glenis", {"mensaje": "¿cuántos jugadores?"}, at)
        self.assertEqual(estado, 400)
        self.assertIn("clave", r["error"].lower())

    def test_el_resumen_cuenta_los_depositos(self):
        token = self.usuario("ana@correo.com")
        self.pedir("/api/deposito", {"importe": "100,00", "referencia": "333333",
                                     "banco": "Banesco", "dia": time.strftime("%Y-%m-%d")}, token)
        at = self.admin()
        _, r = self.pedir("/api/admin/resumen", token=at)
        self.assertEqual(r["depositos_pendientes"], 1)
        self.assertEqual(r["depositos_pendiente_centimos"], 10_000)

    # -- administración --

    def test_solo_el_admin_entra_al_panel(self):
        token = self.usuario("ana@correo.com")
        for ruta in ("/api/admin/resumen", "/api/admin/jugadores", "/api/admin/retiros",
                     "/api/admin/movimientos", "/api/admin/partidas"):
            estado, _ = self.pedir(ruta, token=token)
            self.assertEqual(estado, 403, f"{ruta} debería estar prohibida")

    def test_sin_token_no_entra_al_panel(self):
        estado, _ = self.pedir("/api/admin/resumen")
        self.assertEqual(estado, 403)

    def test_el_admin_ve_el_resumen(self):
        self.usuario("ana@correo.com", recarga="100,00")
        _, r = self.pedir("/api/admin/resumen", token=self.admin())
        self.assertGreaterEqual(r["jugadores"], 1)
        self.assertGreaterEqual(r["total_en_cuentas"], 10_000)

    def test_el_admin_ajusta_saldo(self):
        self.usuario("ana@correo.com")
        at = self.admin()
        self.pedir("/api/admin/ajuste", {"correo": "ana@correo.com", "importe": "50,00", "signo": "sumar"}, at)
        _, j = self.pedir("/api/admin/jugadores", token=at)
        ana = [x for x in j["jugadores"] if x["correo"] == "ana@correo.com"][0]
        self.assertEqual(ana["saldo"], 5_000)

    def test_el_admin_desactiva_a_un_jugador(self):
        self.usuario("ana@correo.com")
        at = self.admin()
        self.pedir("/api/admin/usuario", {"correo": "ana@correo.com", "activo": False}, at)
        estado, _ = self.pedir("/api/entrar", {"correo": "ana@correo.com", "clave": "miClaveSegura1"})
        self.assertEqual(estado, 401)

    def test_el_admin_no_se_desactiva_a_si_mismo(self):
        at = self.admin()
        estado, _ = self.pedir("/api/admin/usuario", {"correo": ADMIN, "activo": False}, at)
        self.assertEqual(estado, 400)

    # -- cuenta a la que el jugador manda el dinero --

    def test_config_trae_la_cuenta_de_pago(self):
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        cuenta = r["cuenta_pago"]
        self.assertTrue(cuenta["configurada"])
        self.assertEqual(cuenta["banco"], "Banco de Venezuela")
        self.assertEqual(cuenta["telefono"], "0416-7677264")
        self.assertEqual(cuenta["cedula"], "12.256.618")

    def test_la_cuenta_de_pago_se_ve_sin_entrar(self):
        """El jugador tiene que verla para poder pagar."""
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        self.assertIn("cuenta_pago", r)

    def test_el_jugador_tambien_ve_la_cuenta(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/config", token=token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["cuenta_pago"]["telefono"], "0416-7677264")

    # -- multi-país --

    def test_el_catalogo_de_paises_se_ve_sin_entrar(self):
        estado, r = self.pedir("/api/paises")
        self.assertEqual(estado, 200)
        self.assertEqual([p["code"] for p in r["paises"]], ["VE", "CO", "CL", "US"])
        # 5 métodos: EE. UU. tiene Cash App y Wise; los demás países, uno cada uno.
        self.assertEqual(len(r["metodos_pago"]), 5)

    def test_config_trae_los_metodos_del_pais_y_las_cuentas_admin(self):
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        # En Venezuela solo hay un método, pero la lista siempre viene.
        self.assertEqual([m["id"] for m in r["metodos_pago"]], ["pago_movil_ve"])
        # Las cuentas de administración van una por país, para el desglose.
        self.assertEqual([c["pais"] for c in r["cuentas_admin"]], ["VE", "CO", "CL", "US"])

    def test_config_trae_el_pais_y_la_moneda(self):
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        self.assertEqual(r["pais"], "VE")
        self.assertEqual(r["moneda"], "VES")
        self.assertEqual(r["simbolo"], "Bs")
        self.assertEqual(r["metodo_pago"]["id"], "pago_movil_ve")

    def test_la_cabecera_de_pais_cambia_la_moneda(self):
        estado, r = self.pedir("/api/config", cabeceras_extra={"X-Pais": "CO"})
        self.assertEqual(estado, 200)
        self.assertEqual(r["pais"], "CO")
        self.assertEqual(r["moneda"], "COP")
        self.assertEqual(r["simbolo"], "$")
        self.assertEqual(r["metodo_pago"]["id"], "nequi_co")

    def test_el_idioma_detecta_el_pais(self):
        estado, r = self.pedir("/api/config", cabeceras_extra={"Accept-Language": "es-CO,es"})
        self.assertEqual(estado, 200)
        self.assertEqual(r["pais"], "CO")

    def test_un_pais_desconocido_cae_en_venezuela(self):
        estado, r = self.pedir("/api/config", cabeceras_extra={"X-Pais": "ZZ"})
        self.assertEqual(estado, 200)
        self.assertEqual(r["pais"], "VE")

    def test_los_importes_se_muestran_en_la_moneda_del_pais(self):
        estado, r = self.pedir("/api/config", cabeceras_extra={"X-Pais": "US"})
        self.assertEqual(estado, 200)
        self.assertTrue(r["deposito_minimo_texto"].startswith("$"))

    def test_el_deposito_guarda_el_pais(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/deposito", {
            "importe": "100,00", "referencia": "123456", "banco": "",
            "dia": time.strftime("%Y-%m-%d"), "metodo": "cashapp", "pais": "US"}, token)
        self.assertEqual(estado, 200, r)
        self.assertEqual(r["deposito"]["pais"], "US")

    # -- la administración cambia los precios de las salas --

    def test_el_admin_cambia_el_precio_de_una_sala(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala/editar",
                               {"sala": "sala-zulia", "precio": "3000,00"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["precio_texto"], "Bs 3.000,00")
        _, salas = self.pedir("/api/salas")
        zulia = [s for s in salas["salas"] if s["id"] == "sala-zulia"][0]
        self.assertEqual(zulia["precio_texto"], "Bs 3.000,00")

    def test_el_precio_nuevo_lo_paga_el_jugador(self):
        at = self.admin()
        self.pedir("/api/admin/sala/editar", {"sala": "sala-tachira", "precio": "250,00"}, at)
        token = self.usuario("ana@correo.com", recarga="1000,00")
        _, r = self.pedir("/api/carton", {"sala": "sala-tachira"}, token)
        self.assertEqual(r["precio"], 25_000)
        self.assertEqual(r["saldo"], 75_000)

    def test_el_admin_renombra_una_sala(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala/editar",
                               {"sala": "sala-miranda", "nombre": "Mérida"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["nombre"], "Mérida")

    def test_solo_el_admin_cambia_los_precios(self):
        token = self.usuario("ana@correo.com")
        estado, _ = self.pedir("/api/admin/sala/editar",
                               {"sala": "sala-zulia", "precio": "1,00"}, token)
        self.assertEqual(estado, 403)
        _, salas = self.pedir("/api/salas")
        zulia = [s for s in salas["salas"] if s["id"] == "sala-zulia"][0]
        self.assertEqual(zulia["precio_texto"], "Bs 2.000,00", "el precio no debió cambiar")

    def test_un_precio_desmedido_se_rechaza(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala/editar",
                               {"sala": "sala-zulia", "precio": "999999,00"}, at)
        self.assertEqual(estado, 400)
        self.assertIn("costar", r["error"])

    def test_no_se_cambia_una_sala_de_jugador_desde_el_panel(self):
        token = self.usuario("ana@correo.com")
        _, s = self.pedir("/api/sala/crear",
                          {"nombre": "La de Ana", "modo": "normal", "precio": "10,00"}, token)
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala/editar",
                               {"sala": s["sala"]["id"], "precio": "20,00"}, at)
        self.assertEqual(estado, 400)
        self.assertIn("jugador", r["error"])


if __name__ == "__main__":
    unittest.main()
