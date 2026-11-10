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

    def test_head_responde_sin_cuerpo(self):
        # Los monitores de disponibilidad y las vistas previas de enlaces usan
        # HEAD: debe responder como GET pero sin cuerpo.
        for ruta in ("/", "/estilos.css", "/app.js", "/api/salud"):
            peticion = urllib.request.Request(
                f"http://127.0.0.1:{self.puerto}{ruta}", method="HEAD")
            with urllib.request.urlopen(peticion, timeout=10) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.read(), b"")

    def test_sin_token_no_hay_saldo(self):
        estado, datos = self.pedir("/api/saldo")
        self.assertEqual(estado, 401)

    # -- juego --

    def test_flujo_completo_de_juego(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        # Se juega en la sala Lara ($ 5 el cartón).
        _, c = self.pedir("/api/carton", {"sala": "sala-lara"}, token)
        self.assertEqual(c["precio"], 500)
        self.assertEqual(c["saldo"], 499_500)
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
        # Tres cartones de $ 5: cobra $ 15 y el saldo baja en consecuencia.
        self.assertEqual(r["saldo"], 498_500)
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
                          {"importe": "500,00", "metodo": "paypal",
                           "detalles": "ana@correo.com"}, token)
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
        _, r = self.pedir("/api/retiro", {"importe": "500,00", "metodo": "paypal",
                                          "detalles": "ana@correo.com"}, token)
        at = self.admin()
        self.pedir("/api/admin/retiro", {"id": r["retiro"]["id"], "accion": "rechazar", "nota": "mal"}, at)
        _, s = self.pedir("/api/saldo", token=token)
        self.assertEqual(s["saldo"], 100_000)

    def test_retiro_sin_saldo(self):
        token = self.usuario("ana@correo.com")
        estado, _ = self.pedir("/api/retiro", {"importe": "500,00", "metodo": "paypal",
                                               "detalles": "ana@correo.com"}, token)
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
        self.assertEqual(sala["precio_texto"], "$ 2,00")

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
        self.assertEqual(saldo["saldo"], 500_000 - 6 * 200)

    def test_pasarse_del_tope_no_deja_media_compra_hecha(self):
        """Si pide 5 y solo le caben 2, no se le cobra nada."""
        token = self.usuario("ana@correo.com", recarga="5000,00")
        self.pedir("/api/carton", {"sala": "sala-ganar-desde-casa", "cantidad": 4}, token)
        estado, err = self.pedir("/api/carton",
                                 {"sala": "sala-ganar-desde-casa", "cantidad": 4}, token)
        self.assertEqual(estado, 400)
        _, saldo = self.pedir("/api/saldo", token=token)
        self.assertEqual(saldo["saldo"], 500_000 - 4 * 200)

    def test_un_jugador_crea_su_sala(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/sala/crear", {
            "nombre": "La de Ana", "modo": "normal", "precio": "25,00", "publica": True}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["precio_texto"], "$ 25,00")
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
        self.assertEqual(r["ganancias"]["anfitrion_texto"], "$ 0,00")

    def test_el_jugador_juega_en_la_sala_que_elige(self):
        token = self.usuario("ana@correo.com", recarga="5000,00")
        _, r = self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        self.assertEqual(r["precio"], 1_000)   # Zulia: $ 10

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
        self.assertEqual(r["evento"]["precio_texto"], "$ 100,00")
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
            "importe": "150,00", "referencia": "123456789", "banco": "",
            "dia": time.strftime("%Y-%m-%d"), "metodo": "paypal"}, token)
        self.assertEqual(estado, 200)
        self.assertEqual(r["deposito"]["estado"], "pendiente")
        # Y todavía no hay dinero.
        self.assertEqual(self.pedir("/api/saldo", token=token)[1]["saldo"], 0)

    def test_declarar_deposito_necesita_entrar(self):
        estado, _ = self.pedir("/api/deposito", {"importe": "100,00", "referencia": "123456",
                                                 "banco": "",
                                                 "dia": time.strftime("%Y-%m-%d")})
        self.assertEqual(estado, 401)

    def test_la_misma_referencia_se_rechaza(self):
        token = self.usuario("ana@correo.com")
        hoy = time.strftime("%Y-%m-%d")
        base = {"importe": "100,00", "referencia": "555555", "banco": "", "dia": hoy}
        self.assertEqual(self.pedir("/api/deposito", base, token)[0], 200)
        self.assertEqual(self.pedir("/api/deposito", base, token)[0], 400)

    def test_el_admin_acredita_el_deposito(self):
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/deposito", {"importe": "150,00", "referencia": "999888",
                                            "banco": "",
                                            "dia": time.strftime("%Y-%m-%d")}, token)
        at = self.admin()
        estado, res = self.pedir("/api/admin/deposito",
                                 {"id": r["deposito"]["id"], "accion": "acreditar"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(res["deposito"]["estado"], "acreditado")
        # De $ 150 la administración retiene su 20 %: entran $ 120 al saldo.
        self.assertEqual(res["deposito"]["comision"], 3_000)
        self.assertEqual(self.pedir("/api/saldo", token=token)[1]["saldo"], 12_000)

    def test_solo_el_admin_acredita(self):
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/deposito", {"importe": "100,00", "referencia": "777777",
                                            "banco": "",
                                            "dia": time.strftime("%Y-%m-%d")}, token)
        estado, _ = self.pedir("/api/admin/deposito",
                               {"id": r["deposito"]["id"], "accion": "acreditar"}, token)
        self.assertEqual(estado, 403)
        self.assertEqual(self.pedir("/api/saldo", token=token)[1]["saldo"], 0)

    def test_el_jugador_ve_sus_depositos(self):
        token = self.usuario("ana@correo.com")
        self.pedir("/api/deposito", {"importe": "100,00", "referencia": "444444",
                                     "banco": "", "dia": time.strftime("%Y-%m-%d")}, token)
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
                                     "banco": "", "dia": time.strftime("%Y-%m-%d")}, token)
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

    # -- a dónde manda el jugador el dinero --

    def test_config_trae_los_metodos_para_pagar(self):
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        # Solo PayPal y USDT, y con la cuenta de la casa a la vista.
        self.assertEqual([m["id"] for m in r["metodos_pago"]], ["paypal", "cripto"])
        paypal = next(m for m in r["metodos_pago"] if m["id"] == "paypal")
        self.assertTrue(paypal["platformAccount"])
        valores = {d["value"] for d in paypal["platformAccount"]}
        self.assertIn("taktak.messenger@gmail.com", valores)

    def test_el_jugador_tambien_ve_los_metodos(self):
        token = self.usuario("ana@correo.com")
        estado, r = self.pedir("/api/config", token=token)
        self.assertEqual(estado, 200)
        self.assertEqual([m["id"] for m in r["metodos_pago"]], ["paypal", "cripto"])

    # -- multi-país --

    def test_el_catalogo_de_paises_se_ve_sin_entrar(self):
        estado, r = self.pedir("/api/paises")
        self.assertEqual(estado, 200)
        self.assertEqual([p["code"] for p in r["paises"]], ["VE", "CO", "CL", "US"])
        # Dos métodos, iguales para todos: PayPal y cripto (USDT).
        self.assertEqual(len(r["metodos_pago"]), 2)

    def test_config_trae_los_metodos_del_pais_y_las_cuentas_admin(self):
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        # Los métodos son los mismos en todos los países.
        self.assertEqual([m["id"] for m in r["metodos_pago"]], ["paypal", "cripto"])
        # La cuenta de administración es una sola para todo el mundo.
        self.assertEqual(len(r["cuentas_admin"]), 1)

    def test_config_trae_el_pais_y_la_moneda(self):
        estado, r = self.pedir("/api/config")
        self.assertEqual(estado, 200)
        self.assertEqual(r["pais"], "VE")
        self.assertEqual(r["moneda"], "USD")
        self.assertEqual(r["simbolo"], "$")
        self.assertEqual(r["metodo_pago"]["id"], "paypal")

    def test_la_cabecera_de_pais_cambia_la_moneda(self):
        estado, r = self.pedir("/api/config", cabeceras_extra={"X-Pais": "CO"})
        self.assertEqual(estado, 200)
        self.assertEqual(r["pais"], "CO")
        # El país cambia el idioma, pero el dinero es siempre el dólar.
        self.assertEqual(r["moneda"], "USD")
        self.assertEqual(r["simbolo"], "$")
        self.assertEqual(r["metodo_pago"]["id"], "paypal")

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
            "dia": time.strftime("%Y-%m-%d"), "metodo": "cripto", "pais": "US"}, token)
        self.assertEqual(estado, 200, r)
        self.assertEqual(r["deposito"]["pais"], "US")

    # -- la administración cambia los precios de las salas --

    def test_el_admin_cambia_el_precio_de_una_sala(self):
        at = self.admin()
        estado, r = self.pedir("/api/admin/sala/editar",
                               {"sala": "sala-zulia", "precio": "3000,00"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["precio_texto"], "$ 3.000,00")
        _, salas = self.pedir("/api/salas")
        zulia = [s for s in salas["salas"] if s["id"] == "sala-zulia"][0]
        self.assertEqual(zulia["precio_texto"], "$ 3.000,00")

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
        self.assertEqual(zulia["precio_texto"], "$ 10,00", "el precio no debió cambiar")

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

    # -- sala de trabajo (la de la casa con anfitrión) --

    def test_la_sala_de_trabajo_es_la_de_ganar_desde_casa(self):
        jugador = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/salas", token=jugador)
        sala = next(s for s in r["salas"] if s["id"] == "sala-ganar-desde-casa")
        self.assertTrue(sala["es_trabajo"])
        self.assertEqual(sala["comision_anfitrion"], 15)
        self.assertEqual(sala["premio_pct"], 80)

    def test_una_sala_de_jugador_reparte_75_10_15(self):
        token = self.usuario("ana@correo.com")
        _, r = self.pedir("/api/sala/crear",
                          {"nombre": "Normal", "modo": "normal", "precio": "10,00"}, token)
        self.assertFalse(r["sala"]["es_trabajo"])
        self.assertEqual(r["sala"]["comision_anfitrion"], 10)
        self.assertEqual(r["sala"]["premio_pct"], 75)

    def test_el_anfitrion_de_la_casa_pone_el_juego_y_el_precio(self):
        at = self.admin()
        estado, r = self.pedir("/api/sala/trabajo",
                               {"sala": "sala-ganar-desde-casa", "precio": "25,00",
                                "tipo_juego": "diagonal"}, at)
        self.assertEqual(estado, 200)
        self.assertEqual(r["sala"]["precio_texto"], "$ 25,00")
        self.assertEqual(r["sala"]["tipo_juego"], "diagonal")

    def test_el_precio_nuevo_de_trabajo_lo_paga_el_jugador(self):
        at = self.admin()
        self.pedir("/api/sala/trabajo",
                   {"sala": "sala-ganar-desde-casa", "precio": "25,00"}, at)
        jugador = self.usuario("luis@correo.com", recarga="100,00")
        _, c = self.pedir("/api/carton", {"sala": "sala-ganar-desde-casa"}, jugador)
        self.assertEqual(c["precio"], 2_500)
        self.assertEqual(c["saldo"], 7_500)

    def test_solo_el_anfitrion_toca_la_sala_de_trabajo(self):
        otro = self.usuario("luis@correo.com")
        estado, _ = self.pedir("/api/sala/trabajo",
                               {"sala": "sala-ganar-desde-casa", "precio": "25,00"}, otro)
        self.assertEqual(estado, 400)

    def test_al_entrar_a_la_sala_de_trabajo_el_anfitrion_se_reconoce(self):
        at = self.admin()
        _, r = self.pedir("/api/sala/entrar", {"sala": "sala-ganar-desde-casa"}, at)
        self.assertTrue(r["partida"]["es_trabajo"])
        self.assertTrue(r["partida"]["soy_dueno"])
        self.assertEqual(r["partida"]["reparto"]["comision_pct"], 15)

    def test_la_sala_de_trabajo_reparte_80_15_5(self):
        at = self.admin()
        jugador = self.usuario("luis@correo.com", recarga="100,00")
        self.pedir("/api/carton", {"sala": "sala-ganar-desde-casa"}, jugador)
        _, r = self.pedir("/api/sala/entrar", {"sala": "sala-ganar-desde-casa"}, at)
        reparto = r["partida"]["reparto"]
        self.assertEqual(reparto["bote"], 2_00)
        self.assertEqual(reparto["premio"], 1_60)
        self.assertEqual(reparto["anfitrion"], 30)
        self.assertEqual(reparto["app"], 10)

    # -- referidos --

    def test_referido_cobra_comision_al_ganar_el_ahijado(self):
        """El camino real: padrino invita, el ahijado gana y el padrino cobra."""
        padrino = self.usuario("padrino@correo.com")
        _, r = self.pedir("/api/referidos", token=padrino)
        codigo = r["codigo"]
        self.assertTrue(codigo)

        # El ahijado se registra con el código del padrino y entra con plata.
        self.pedir("/api/registro", {"correo": "ahijado@correo.com",
                                     "clave": "miClaveSegura1", "codigo_amigo": codigo})
        _, d = self.pedir("/api/entrar", {"correo": "ahijado@correo.com",
                                          "clave": "miClaveSegura1"})
        ahijado = d["token"]
        self.pedir("/api/recargar", {"correo": "ahijado@correo.com", "importe": "5000,00"},
                   self.admin())

        # Juega en Nueva Esparta (diagonal, Bs 50 el cartón) y canta bingo.
        _, c = self.pedir("/api/carton", {"sala": "sala-nueva-esparta"}, ahijado)
        self.pedir("/api/bola", {"sala": "sala-nueva-esparta"}, ahijado)
        self._marcar_patron("sala-nueva-esparta", c["carton"], "diagonal")
        estado, res = self.pedir("/api/bingo", {"sala": "sala-nueva-esparta",
                                                "carton": c["carton"]}, ahijado)
        self.assertEqual(estado, 200, res)
        self.assertGreater(res["app"], 0, "la app debió ganar algo en la partida")

        # El padrino cobra el 10 % de la parte de la app.
        _, s = self.pedir("/api/saldo", token=padrino)
        esperado = res["app"] * 10 // 100
        self.assertEqual(s["saldo"], esperado)
        _, rr = self.pedir("/api/referidos", token=padrino)
        self.assertEqual(rr["invitados"], 1)
        self.assertEqual(rr["total"], esperado)

    def test_el_padrino_no_cobra_si_el_ahijado_no_gana(self):
        padrino = self.usuario("padrino2@correo.com")
        _, r = self.pedir("/api/referidos", token=padrino)
        self.pedir("/api/registro", {"correo": "ahijado2@correo.com",
                                     "clave": "miClaveSegura1", "codigo_amigo": r["codigo"]})
        _, d = self.pedir("/api/entrar", {"correo": "ahijado2@correo.com",
                                          "clave": "miClaveSegura1"})
        ahijado = d["token"]
        self.pedir("/api/recargar", {"correo": "ahijado2@correo.com", "importe": "5000,00"},
                   self.admin())
        # Compra cartón y saca una bola, pero no canta: no hay comisión.
        self.pedir("/api/carton", {"sala": "sala-nueva-esparta"}, ahijado)
        self.pedir("/api/bola", {"sala": "sala-nueva-esparta"}, ahijado)
        _, s = self.pedir("/api/saldo", token=padrino)
        self.assertEqual(s["saldo"], 0)

    def test_un_codigo_de_amigo_que_no_existe_se_rechaza(self):
        estado, r = self.pedir("/api/registro", {"correo": "tarde@correo.com",
                                                 "clave": "miClaveSegura1",
                                                 "codigo_amigo": "NOEXISTE"})
        self.assertEqual(estado, 400)
        self.assertIn("código", r["error"].lower())

    def test_el_admin_ve_los_referidos_pagados(self):
        padrino = self.usuario("padrino3@correo.com")
        _, r = self.pedir("/api/referidos", token=padrino)
        self.pedir("/api/registro", {"correo": "ahijado3@correo.com",
                                     "clave": "miClaveSegura1", "codigo_amigo": r["codigo"]})
        _, d = self.pedir("/api/entrar", {"correo": "ahijado3@correo.com",
                                          "clave": "miClaveSegura1"})
        ahijado = d["token"]
        self.pedir("/api/recargar", {"correo": "ahijado3@correo.com", "importe": "5000,00"},
                   self.admin())
        _, c = self.pedir("/api/carton", {"sala": "sala-nueva-esparta"}, ahijado)
        self.pedir("/api/bola", {"sala": "sala-nueva-esparta"}, ahijado)
        self._marcar_patron("sala-nueva-esparta", c["carton"], "diagonal")
        self.pedir("/api/bingo", {"sala": "sala-nueva-esparta", "carton": c["carton"]}, ahijado)

        estado, panel = self.pedir("/api/admin/referidos", token=self.admin())
        self.assertEqual(estado, 200)
        self.assertEqual(len(panel["referidos"]), 1)
        self.assertEqual(panel["referidos"][0]["padrino"], "padrino3@correo.com")
        self.assertEqual(panel["pct"], 10)
        # La economía por país es una lista, no un objeto: si no, la tabla del
        # panel de referidos sale siempre vacía.
        self.assertIsInstance(panel["economia_pais"], list)
        if panel["economia_pais"]:
            self.assertIn("app_texto", panel["economia_pais"][0])

    def test_el_panel_de_referidos_es_solo_para_admin(self):
        token = self.usuario("curioso@correo.com")
        estado, _ = self.pedir("/api/admin/referidos", token=token)
        self.assertEqual(estado, 403)

    def test_una_cuenta_sin_codigo_recibe_uno_al_pedir_sus_referidos(self):
        # El caso real: una cuenta creada antes de los referidos (o la de
        # administración) no trae código. Al pedir sus referidos se le genera.
        token = self.usuario("antigua@correo.com")
        self.almacen.fijar_codigo_amigo("antigua@correo.com", "")
        estado, d = self.pedir("/api/referidos", token=token)
        self.assertEqual(estado, 200)
        self.assertTrue(d["codigo"], "la cuenta se quedó sin código de amigo")
        # Y queda guardado: la segunda vez es el mismo.
        _, d2 = self.pedir("/api/referidos", token=token)
        self.assertEqual(d2["codigo"], d["codigo"])

    # -- foto de perfil --

    FOTO = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlE"
            "QVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

    def test_sin_foto_la_sesion_no_trae_url(self):
        token = self.usuario("sinfoto@correo.com")
        _, s = self.pedir("/api/sesion", token=token)
        self.assertEqual(s["foto_url"], "")

    def test_guardar_y_servir_la_foto(self):
        token = self.usuario("confoto@correo.com")
        estado, d = self.pedir("/api/foto", {"foto": self.FOTO}, token)
        self.assertEqual(estado, 200)
        self.assertTrue(d["foto_url"])
        # La sesión ya la anuncia.
        _, s = self.pedir("/api/sesion", token=token)
        self.assertEqual(s["foto_url"], d["foto_url"])
        # Y se sirve como imagen de verdad.
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.puerto}{d['foto_url']}", timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertTrue(r.headers["Content-Type"].startswith("image/"))
            self.assertGreater(len(r.read()), 0)

    def test_la_mesa_muestra_nombre_y_foto_del_jugador(self):
        token = self.usuario("mesa@correo.com", recarga="5000,00")
        self.pedir("/api/foto", {"foto": self.FOTO}, token)
        self.pedir("/api/sala/entrar", {"sala": "sala-zulia"}, token)
        self.pedir("/api/carton", {"sala": "sala-zulia"}, token)
        _, vista = self.pedir("/api/partida")
        fila = next(f for f in vista["a_cuanto_estan"] if f["jugador"] == "mesa@correo.com")
        self.assertEqual(fila["nombre"], "mesa")
        self.assertTrue(fila["foto_url"])

    def test_la_foto_no_puede_ser_cualquier_cosa(self):
        token = self.usuario("malafoto@correo.com")
        estado, _ = self.pedir("/api/foto", {"foto": "hola"}, token)
        self.assertEqual(estado, 400)
        estado, _ = self.pedir("/api/foto", {"foto": "data:image/png;base64,###"}, token)
        self.assertEqual(estado, 400)
        # Una foto enorme se rechaza, y no deja la cuenta sin la que ya tenía.
        self.pedir("/api/foto", {"foto": self.FOTO}, token)
        enorme = "data:image/png;base64," + "A" * 500_000
        estado, _ = self.pedir("/api/foto", {"foto": enorme}, token)
        self.assertEqual(estado, 400)
        _, s = self.pedir("/api/sesion", token=token)
        self.assertTrue(s["foto_url"], "un rechazo borró la foto buena")

    def test_la_foto_necesita_sesion(self):
        estado, _ = self.pedir("/api/foto", {"foto": self.FOTO})
        self.assertEqual(estado, 401)

    def test_quitar_la_foto(self):
        token = self.usuario("quitarfoto@correo.com")
        self.pedir("/api/foto", {"foto": self.FOTO}, token)
        _, d = self.pedir("/api/foto", {"foto": ""}, token)
        self.assertEqual(d["foto_url"], "")
        _, s = self.pedir("/api/sesion", token=token)
        self.assertEqual(s["foto_url"], "")

    def test_billetera_desafio_y_vincular(self):
        import json as _json
        import time
        from tests.test_billeteras import EVM_DIRECCION, EVM_FIRMA, NONCE

        correo = "ana@correo.com"
        token = self.usuario(correo)

        # Desafío por HTTP: trae un mensaje para firmar con el correo dentro.
        estado, d = self.pedir("/api/billetera/desafio", {}, token)
        self.assertEqual(estado, 200)
        self.assertTrue(d["ok"])
        self.assertIn(correo, d["mensaje"])

        # Con una firma que no corresponde, no se vincula.
        estado, _ = self.pedir("/api/billetera",
                               {"direccion": EVM_DIRECCION, "firma": "00" * 65}, token)
        self.assertNotEqual(estado, 200)

        # Con el desafío fijado al nonce del vector, la firma buena sí vincula.
        self.almacen.guardar_meta("billetera_desafio:" + correo,
                                  _json.dumps({"nonce": NONCE,
                                               "caduca": time.time() + 300}))
        estado, d = self.pedir("/api/billetera",
                               {"direccion": EVM_DIRECCION, "firma": EVM_FIRMA}, token)
        self.assertEqual(estado, 200)
        self.assertTrue(d["ok"])
        _, d = self.pedir("/api/billetera", token=token)
        self.assertTrue(d["billetera"]["configurada"])
        self.assertEqual(d["billetera"]["direccion"], EVM_DIRECCION)

        # Se puede desvincular.
        self.pedir("/api/billetera/borrar", {}, token)
        _, d = self.pedir("/api/billetera", token=token)
        self.assertIsNone(d["billetera"])

    def test_billetera_requiere_sesion(self):
        estado, _ = self.pedir("/api/billetera")
        self.assertEqual(estado, 401)
        estado, _ = self.pedir("/api/billetera/desafio", {})
        self.assertEqual(estado, 401)

    def _marcar_patron(self, sala_id, carton_id, patron):
        """Marca en el cartón el patrón de la partida, para poder cantar bingo.

        Se hace sobre el estado real del servidor (el mismo proceso), que es lo
        único que la cantada comprueba: no se puede falsear por HTTP.
        """
        from bingo.cartones import PATRONES
        with self.juego.candado:
            partida = self.juego.mesa.sala.partidas[self.juego._partida_id]
            partida.cartones[carton_id].marcados |= PATRONES[patron]


if __name__ == "__main__":
    unittest.main()
