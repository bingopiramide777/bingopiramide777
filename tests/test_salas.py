"""Pruebas de las salas y del reparto del dinero.

Esta es la parte donde un error cuesta dinero de verdad, así que se prueban a
fondo los céntimos: que nada se pierda y que nadie cobre de más.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from bingo import MesaBingo, Sala as SalaBingo
from nucleo.almacen import Almacen
from nucleo.monedero import Monedero
from nucleo.money import a_texto
from nucleo.usuarios import Usuarios
from nucleo.salas import (
    COMISION_ANFITRION,
    COMISION_TRABAJO,
    PREMIO_CASA,
    PREMIO_CON_ANFITRION,
    PREMIO_TRABAJO,
    SALA_CASA_ID,
    SALA_CASA_NOMBRE,
    SALA_CASA_PRECIO,
    SALA_CASA_PRECIO_ANTIGUO,
    SALAS_INICIALES_ANTIGUAS,
    ErrorDeSalas,
    Salas,
    reparto_del_bote,
    reparto_evento,
    reparto_por_puestos,
)


class RepartoTest(unittest.TestCase):
    """El reparto del bote: la cuenta más delicada del programa."""

    def test_sala_de_la_casa_gana_80_20(self):
        r = reparto_del_bote(10_000, con_anfitrion=False)
        self.assertEqual(r["premio"], 8_000)
        self.assertEqual(r["anfitrion"], 0)
        self.assertEqual(r["app"], 2_000)

    def test_sala_de_jugador_reparte_70_10_20(self):
        r = reparto_del_bote(10_000, con_anfitrion=True)
        self.assertEqual(r["premio"], 7_000)
        self.assertEqual(r["anfitrion"], 1_000)
        self.assertEqual(r["app"], 2_000)

    def test_sala_de_trabajo_reparte_80_15_5(self):
        r = reparto_del_bote(10_000, con_anfitrion=True, comision_pct=15,
                             premio_pct=Decimal("0.80"))
        self.assertEqual(r["premio"], 8_000)
        self.assertEqual(r["anfitrion"], 1_500)
        self.assertEqual(r["app"], 500)

    def test_el_reparto_nunca_pierde_un_centimo(self):
        """Ni con botes de céntimos raros: premio + anfitrión + app = bote."""
        for bote in range(0, 20_000):
            for con in (True, False):
                r = reparto_del_bote(bote, con_anfitrion=con)
                self.assertEqual(r["premio"] + r["anfitrion"] + r["app"], bote,
                                 f"no cuadra con bote {bote} (anfitrión={con})")

    def test_la_app_nunca_pierde_dinero(self):
        for bote in range(0, 20_000):
            for con in (True, False):
                self.assertGreaterEqual(reparto_del_bote(bote, con)["app"], 0)

    def test_bote_negativo_o_no_entero_se_rechaza(self):
        with self.assertRaises(ErrorDeSalas):
            reparto_del_bote(-1, con_anfitrion=False)
        with self.assertRaises(ErrorDeSalas):
            reparto_del_bote(10.5, con_anfitrion=False)


class SalasTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)

    def test_vienen_las_salas_de_la_casa(self):
        nombres = [s.nombre for s in self.salas.de_la_casa()]
        self.assertEqual(nombres, ["Zulia", "Lara", "Carabobo", "Mérida", "Táchira",
                                   "Nueva Esparta"])
        self.assertTrue(all(not s.es_de_jugador for s in self.salas.de_la_casa()))

    def test_viene_la_sala_de_jugar_desde_casa(self):
        """La sala para trabajar desde casa: cartón lleno y 6 cartones por jugador."""
        sala = self.salas.de(SALA_CASA_ID)
        self.assertEqual(sala.nombre, SALA_CASA_NOMBRE)
        self.assertEqual(sala.modo, "carton_lleno")
        self.assertEqual(sala.tipo_juego, "carton_lleno")
        self.assertEqual(sala.precio_carton, 2_00)
        self.assertEqual(sala.max_cartones, 6)
        # Sin anfitrión configurado sigue siendo de la casa (80/20).
        self.assertFalse(sala.es_de_jugador)
        self.assertFalse(sala.es_trabajo)

    def test_viene_la_sala_de_eventos_lago_de_maracaibo(self):
        evento = self.salas.evento()
        self.assertTrue(evento.es_evento)
        self.assertEqual(evento.nombre, "Sala de Eventos Lago de Maracaibo")
        self.assertEqual(evento.aforo, 50)
        self.assertEqual(list(evento.premios_pct), [60, 15, 5])
        self.assertEqual(evento.plazas, 3)

    def test_cada_sala_tiene_su_precio_y_su_modo(self):
        """Los precios que fijó la administración, de la más barata a la más cara."""
        precios = {s.nombre: s.precio_carton for s in self.salas.de_la_casa()}
        self.assertEqual(precios, {
            "Zulia": 10_00,
            "Lara": 5_00,
            "Carabobo": 3_00,
            "Mérida": 2_00,
            "Táchira": 1_00,
            "Nueva Esparta": 1_00,
        })
        modos = {s.nombre: s.modo for s in self.salas.de_la_casa()}
        self.assertEqual(modos["Carabobo"], "carton_lleno")
        # Zulia y Lara son de cartón lleno: sus partidas duran más.
        self.assertEqual(modos["Zulia"], "carton_lleno")
        self.assertEqual(modos["Lara"], "carton_lleno")

    def test_un_jugador_crea_su_sala(self):
        s = self.salas.crear("ana@correo.com", "La de Ana", "normal", "25,00")
        self.assertTrue(s.es_de_jugador)
        self.assertEqual(s.dueno, "ana@correo.com")
        self.assertEqual(s.precio_carton, 2_500)
        self.assertEqual(s.comision_anfitrion, 10)
        self.assertIn(s, self.salas.de_dueno("ana@correo.com"))

    def test_la_sala_del_jugador_paga_al_anfitrion(self):
        s = self.salas.crear("ana@correo.com", "La de Ana", "normal", "10,00")
        r = s.reparto(10_000)
        self.assertEqual(r["anfitrion"], 1_000)

    def test_no_se_puede_repetir_un_nombre_de_la_casa(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Zulia", "normal", "10,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Sala de Eventos Lago de Maracaibo",
                             "normal", "10,00")

    def test_el_precio_del_carton_tiene_limites(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Cara", "normal", "1000,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Barata", "normal", "0,50")

    def test_modo_inventado_se_rechaza(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Rara", "modo_raro", "10,00")

    def test_nombre_vacio_se_rechaza(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "   ", "normal", "10,00")

    def test_como_mucho_tres_salas_por_jugador(self):
        for i in range(3):
            self.salas.crear("ana@correo.com", f"Sala {i}", "normal", "10,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Sala 4", "normal", "10,00")

    def test_solo_el_dueno_cierra_su_sala(self):
        s = self.salas.crear("ana@correo.com", "La de Ana", "normal", "10,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.cerrar(s.id, "otro@correo.com")
        self.salas.cerrar(s.id, "ana@correo.com")
        self.assertFalse(self.salas.de(s.id).activa)

    def test_el_admin_cierra_cualquier_sala(self):
        s = self.salas.crear("ana@correo.com", "La de Ana", "normal", "10,00")
        self.salas.cerrar(s.id, "admin@correo.com", es_admin=True)
        self.assertFalse(self.salas.de(s.id).activa)

    def test_sala_que_no_existe(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.de("sala-inventada")

    def test_las_salas_sobreviven_al_reinicio(self):
        self.salas.crear("ana@correo.com", "La de Ana", "competencia", "15,00")
        otra = Salas(self.almacen)
        self.assertEqual(len(otra.de_dueno("ana@correo.com")), 1)


class ConfigurarSalasTest(unittest.TestCase):
    """La administración cambia precios y nombres sin tocar el repositorio."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)

    def test_el_admin_cambia_el_precio_de_una_sala_de_la_casa(self):
        sala = self.salas.configurar_sala("sala-zulia", precio="3500,00")
        self.assertEqual(sala.precio_carton, 350_000)
        # Y queda guardado: al volver a leerla, sigue el precio nuevo.
        self.assertEqual(self.salas.de("sala-zulia").precio_carton, 350_000)

    def test_el_precio_nuevo_sobrevive_al_reinicio(self):
        self.salas.configurar_sala("sala-lara", precio="1500,00")
        otra = Salas(self.almacen)
        self.assertEqual(otra.de("sala-lara").precio_carton, 150_000)

    def test_el_admin_renombra_una_sala(self):
        sala = self.salas.configurar_sala("sala-miranda", nombre="Mérida")
        self.assertEqual(sala.nombre, "Mérida")

    def test_la_sala_de_la_casa_admite_precios_altos(self):
        """🫰 50.000 no cabe en el tope de las salas de jugador, pero sí aquí."""
        sala = self.salas.configurar_sala("sala-zulia", precio="50000,00")
        self.assertEqual(sala.precio_carton, 5_000_000)

    def test_un_precio_desmedido_se_rechaza(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala("sala-zulia", precio="200000,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala("sala-zulia", precio="0,50")

    def test_un_nombre_vacio_se_rechaza(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala("sala-zulia", nombre="   ")

    def test_no_se_tocan_las_salas_de_jugador(self):
        s = self.salas.crear("ana@correo.com", "La de Ana", "normal", "10,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala(s.id, precio="20,00")

    def test_la_sala_de_evento_se_configura_por_su_lado(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala("sala-evento-lago", precio="100,00")

    def test_los_precios_de_las_salas_de_jugador_siguen_limitados(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Cara", "normal", "1000,00")

    def test_el_admin_pone_el_tope_de_cartones_por_jugador(self):
        """El tope por jugador se cambia desde el panel, como el precio."""
        sala = self.salas.configurar_sala(SALA_CASA_ID, max_cartones=6)
        self.assertEqual(sala.max_cartones, 6)
        # Y queda guardado: al volver a leerla, sigue el tope.
        self.assertEqual(self.salas.de(SALA_CASA_ID).max_cartones, 6)

    def test_el_tope_por_jugador_tiene_limites(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala(SALA_CASA_ID, max_cartones=-1)
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_sala(SALA_CASA_ID, max_cartones="muchos")

    def test_el_tope_por_jugador_sobrevive_al_reinicio(self):
        self.salas.configurar_sala(SALA_CASA_ID, max_cartones=4)
        otra = Salas(self.almacen)
        self.assertEqual(otra.de(SALA_CASA_ID).max_cartones, 4)


class SalaTrabajoTest(unittest.TestCase):
    """La sala de trabajo: "Ganar Dinero Desde Casa" con anfitrión de la casa."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.usuarios = Usuarios(self.almacen)
        self.anfitrion = "bingopiramide777@gmail.com"
        self.salas = Salas(self.almacen, usuarios=self.usuarios,
                           anfitrion_casa=self.anfitrion)

    def _trabajo(self):
        return self.salas.de(SALA_CASA_ID)

    def test_la_sala_de_trabajo_es_la_de_ganar_desde_casa(self):
        s = self._trabajo()
        self.assertTrue(s.es_trabajo)
        self.assertTrue(s.es_de_jugador)
        self.assertEqual(s.dueno, self.anfitrion)
        self.assertEqual(s.comision_anfitrion, 15)

    def test_la_sala_de_trabajo_reparte_80_15_5(self):
        s = self._trabajo()
        r = s.reparto(10_000)
        self.assertEqual(r["premio"], 8_000)
        self.assertEqual(r["anfitrion"], 1_500)
        self.assertEqual(r["app"], 500)

    def test_una_sala_de_jugador_reparte_70_10_20(self):
        s = self.salas.crear("ana@correo.com", "Normal", "normal", "10,00")
        self.assertFalse(s.es_trabajo)
        self.assertEqual(s.comision_anfitrion, 10)
        r = s.reparto(10_000)
        self.assertEqual(r["premio"], 7_000)
        self.assertEqual(r["anfitrion"], 1_000)
        self.assertEqual(r["app"], 2_000)

    def test_el_reparto_de_trabajo_nunca_pierde_un_centimo(self):
        s = self._trabajo()
        for bote in range(0, 5_000):
            r = s.reparto(bote)
            self.assertEqual(r["premio"] + r["anfitrion"] + r["app"], bote)

    def test_el_dueno_pone_el_juego_y_el_precio(self):
        s = self._trabajo()
        nueva = self.salas.configurar_trabajo(s.id, self.anfitrion,
                                              precio="25,00", tipo_juego="diagonal")
        self.assertEqual(nueva.precio_carton, 2_500)
        self.assertEqual(nueva.tipo_juego, "diagonal")

    def test_solo_el_dueno_toca_la_sala_de_trabajo(self):
        s = self._trabajo()
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_trabajo(s.id, "otro@correo.com", precio="25,00")

    def test_no_se_configura_una_sala_que_no_es_de_trabajo(self):
        s = self.salas.crear("ana@correo.com", "Normal", "normal", "10,00")
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_trabajo(s.id, "ana@correo.com", precio="25,00")

    def test_el_precio_de_trabajo_respeta_los_limites(self):
        s = self._trabajo()
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_trabajo(s.id, self.anfitrion, precio="1000,00")

    def test_el_juego_inventado_se_rechaza(self):
        s = self._trabajo()
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_trabajo(s.id, self.anfitrion, tipo_juego="inventado")

    def test_la_comision_de_la_sala_de_trabajo_llega_al_monedero(self):
        s = self._trabajo()
        self.assertEqual(self.salas.comision_de_sala(s.id), 15)

    def test_la_sala_de_trabajo_sobrevive_al_reinicio(self):
        s = self._trabajo()
        otra = Salas(self.almacen, usuarios=self.usuarios,
                     anfitrion_casa=self.anfitrion)
        self.assertTrue(otra.de(s.id).es_trabajo)
        self.assertEqual(otra.de(s.id).dueno, self.anfitrion)

    def test_la_sala_de_trabajo_no_esta_entre_las_de_la_casa(self):
        self.assertNotIn(self._trabajo(), self.salas.de_la_casa())

    def test_el_admin_configura_la_sala_de_trabajo(self):
        """Desde el panel se toca como cualquier sala de la casa."""
        s = self.salas.configurar_sala(SALA_CASA_ID, precio="50,00", tipo_juego="linea_h1")
        self.assertEqual(s.precio_carton, 5_000)
        self.assertEqual(s.tipo_juego, "linea_h1")

    def test_sin_anfitrion_la_sala_es_de_la_casa(self):
        almacen = Almacen(":memory:")
        salas = Salas(almacen, usuarios=Usuarios(almacen))
        s = salas.de(SALA_CASA_ID)
        self.assertFalse(s.es_trabajo)
        self.assertFalse(s.es_de_jugador)


class MigracionJuegosTest(unittest.TestCase):
    """Bases de datos viejas: Zulia y Lara pasan a cartón lleno una vez."""

    def test_zulia_y_lara_pasan_a_carton_lleno(self):
        almacen = Almacen(":memory:")
        almacen.guardar_sala({
            "id": "sala-zulia", "nombre": "Zulia", "modo": "normal",
            "precio_carton": 10_00, "tipo_juego": "linea_h1", "dueno": "",
            "publica": 1, "creada": 0.0, "activa": 1,
        })
        almacen.guardar_sala({
            "id": "sala-lara", "nombre": "Lara", "modo": "competencia",
            "precio_carton": 5_00, "tipo_juego": "cuatro_esquinas", "dueno": "",
            "publica": 1, "creada": 0.0, "activa": 1,
        })
        salas = Salas(almacen)
        self.assertEqual(salas.de("sala-zulia").modo, "carton_lleno")
        self.assertEqual(salas.de("sala-zulia").tipo_juego, "carton_lleno")
        self.assertEqual(salas.de("sala-lara").modo, "carton_lleno")
        self.assertEqual(salas.de("sala-lara").tipo_juego, "carton_lleno")

    def test_no_se_pisa_un_juego_que_cambio_el_admin(self):
        almacen = Almacen(":memory:")
        almacen.guardar_sala({
            "id": "sala-zulia", "nombre": "Zulia", "modo": "competencia",
            "precio_carton": 10_00, "tipo_juego": "diagonal", "dueno": "",
            "publica": 1, "creada": 0.0, "activa": 1,
        })
        salas = Salas(almacen)
        self.assertEqual(salas.de("sala-zulia").modo, "competencia")
        self.assertEqual(salas.de("sala-zulia").tipo_juego, "diagonal")

    def test_la_migracion_de_juegos_solo_corre_una_vez(self):
        almacen = Almacen(":memory:")
        Salas(almacen)
        Salas(almacen).configurar_sala("sala-zulia", tipo_juego="diagonal")
        otra = Salas(almacen)
        self.assertEqual(otra.de("sala-zulia").tipo_juego, "diagonal")


class MigracionPreciosTest(unittest.TestCase):
    """Bases de datos viejas: los precios suben una vez, sin pisar al admin."""

    def test_los_precios_viejos_se_actualizan(self):
        almacen = Almacen(":memory:")
        # Una base como la de antes: precios en bolívares y la sala llamada Miranda.
        for id_, viejo in SALAS_INICIALES_ANTIGUAS.items():
            almacen.guardar_sala({
                "id": id_, "nombre": "Miranda" if id_ == "sala-miranda" else id_,
                "modo": "normal", "precio_carton": viejo, "dueno": "", "publica": 1,
                "creada": 0.0, "activa": 1, "es_evento": 0, "aforo": 0, "premios_pct": "",
            })
        salas = Salas(almacen)
        self.assertEqual(salas.de("sala-zulia").precio_carton, 10_00)
        self.assertEqual(salas.de("sala-tachira").precio_carton, 1_00)
        self.assertEqual(salas.de("sala-miranda").nombre, "Mérida")
        self.assertEqual(salas.de("sala-miranda").precio_carton, 2_00)

    def test_la_sala_de_casa_baja_de_bolivares_a_dolares(self):
        almacen = Almacen(":memory:")
        almacen.guardar_sala({
            "id": SALA_CASA_ID, "nombre": SALA_CASA_NOMBRE, "modo": "carton_lleno",
            "precio_carton": SALA_CASA_PRECIO_ANTIGUO, "dueno": "", "publica": 1,
            "creada": 0.0, "activa": 1, "es_evento": 0, "aforo": 0, "premios_pct": "",
        })
        salas = Salas(almacen)
        self.assertEqual(salas.de(SALA_CASA_ID).precio_carton, SALA_CASA_PRECIO)

    def test_no_se_pisa_un_precio_que_cambio_el_admin(self):
        almacen = Almacen(":memory:")
        almacen.guardar_sala({
            "id": "sala-zulia", "nombre": "Zulia", "modo": "normal",
            "precio_carton": 7_777, "dueno": "", "publica": 1, "creada": 0.0,
            "activa": 1, "es_evento": 0, "aforo": 0, "premios_pct": "",
        })
        salas = Salas(almacen)
        self.assertEqual(salas.de("sala-zulia").precio_carton, 7_777)

    def test_la_migracion_solo_corre_una_vez(self):
        almacen = Almacen(":memory:")
        Salas(almacen)
        Salas(almacen).configurar_sala("sala-zulia", precio="3000,00")
        # Volver a montar las salas no debe devolver el precio a 2.000.
        otra = Salas(almacen)
        self.assertEqual(otra.de("sala-zulia").precio_carton, 300_000)


class EconomiaTest(unittest.TestCase):
    """El dinero que deja el bingo, contado desde partidas reales."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)
        self.monedero = Monedero(self.almacen)

    def _jugar(self, sala_id, jugadores, quien_gana=0):
        """Juega una partida entera en una sala y devuelve el resultado del bingo."""
        from bingo.cartones import patron_cumplido

        sala = self.salas.de(sala_id)
        bingo = SalaBingo()
        def reparto(pid, bote):
            r = self.salas.de(sala_id).reparto(bote)
            r["anfitrion_correo"] = self.salas.de(sala_id).dueno
            return r

        mesa = MesaBingo(sala=bingo, monedero=self.monedero, repartidor=reparto)
        partida = bingo.abrir_partida(sala.precio_carton / 100, patron="linea_h1", sala=sala.id)
        cartones = {}
        for j in jugadores:
            self.monedero.recargar(j, 1_000_000, "prueba")
            cid, _ = mesa.comprar_carton(partida.id, j)
            cartones[j] = cid
        bingo.empezar(partida.id)
        # Se sacan bolas hasta que el cartón elegido tenga su línea.
        ganador = jugadores[quien_gana]
        for _ in range(75):
            bingo.sacar_bola(partida.id)
            if patron_cumplido(partida.cartones[cartones[ganador]], "linea_h1"):
                break
        res = mesa.resolver_cantada(partida.id, ganador, cartones[ganador])
        self.almacen.guardar_partida({
            "id": partida.id, "sala": sala.id, "patron": partida.patron,
            "precio_carton": partida.precio_carton, "estado": "terminada",
            "bolas": ",".join(str(b) for b in partida.bombo.sacadas),
            "ganador": ganador, "carton_ganador": cartones[ganador],
            "premio": res["premio"], "empezada": 0.0, "terminada": 1.0,
        })
        for j, cid in cartones.items():
            self.almacen.guardar_carton(cid, partida.id, j, "1|2|3|4|5;1|2|3|4|5;1|2|3|4|5;1|2|3|4|5;1|2|3|4|5")
        return res

    def test_sala_de_la_casa_reparte_80_20(self):
        res = self._jugar("sala-lara", ["ana@correo.com", "luis@correo.com"])
        # 2 cartones x $ 5 = $ 10 de bote
        self.assertEqual(res["bote"], 1_000)
        self.assertEqual(res["premio"], 800)
        self.assertEqual(res["anfitrion"], 0)
        self.assertEqual(res["app"], 200)

    def test_sala_de_jugador_paga_al_anfitrion(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        res = self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        self.assertEqual(res["bote"], 2_000)
        # Sala de jugador: ganador 70 %, anfitrión 10 %, app 20 %.
        self.assertEqual(res["premio"], 1_400)
        self.assertEqual(res["anfitrion"], 200)
        self.assertEqual(res["app"], 400)

    def test_el_anfitrion_cobra_su_comision_en_el_monedero(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        self.assertEqual(self.monedero.saldo("duena@correo.com"), 200)

    def test_el_ganador_cobra_su_premio(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        antes = 1_000_000 - 1_000
        res = self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"], quien_gana=0)
        self.assertEqual(self.monedero.saldo("ana@correo.com"), antes + res["premio"])

    def test_las_ganancias_del_anfitrion_se_cuentan(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        g = self.salas.ganancias("duena@correo.com")
        self.assertEqual(g["partidas"], 2)
        self.assertEqual(g["botes"], 4_000)
        # Sala de jugador: el anfitrión se lleva el 10 % y la app el 20 %.
        self.assertEqual(g["anfitrion"], 400)
        self.assertEqual(g["app"], 800)

    def test_la_economia_suma_todas_las_salas(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        self._jugar("sala-lara", ["ana@correo.com", "luis@correo.com"])
        self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        e = self.salas.economia()
        self.assertEqual(e["partidas"], 2)
        # Lara ($ 5 el cartón, 2 cartones = $ 10) + la sala de la dueña ($ 10 el
        # cartón, 2 cartones = $ 20): 3.000 céntimos.
        self.assertEqual(e["botes"], 3_000)
        # Lara 80 % (800) + sala de jugador 70 % (1.400) = 2.200 de premios.
        self.assertEqual(e["premios"], 2_200)
        self.assertEqual(e["comisiones"], 200)
        # Lara 200 + sala de jugador 400 = 600 para la app.
        self.assertEqual(e["app"], 600)
        # Y el reparto siempre cuadra.
        self.assertEqual(e["premios"] + e["comisiones"] + e["app"], e["botes"])

    def test_sin_partidas_no_hay_ganancias(self):
        e = self.salas.economia()
        self.assertEqual(e["app"], 0)
        self.assertEqual(e["botes"], 0)
        self.assertEqual(a_texto(e["app"]), "🫰 0,00")

    def test_los_porcentajes_son_los_documentados(self):
        # Sala de la casa: 80 % al ganador y 20 % para la app.
        self.assertEqual(PREMIO_CASA, Decimal("0.80"))
        # Sala de jugador: 70 % al ganador, 10 % al anfitrión y 20 % para la app.
        self.assertEqual(PREMIO_CON_ANFITRION, Decimal("0.70"))
        self.assertEqual(COMISION_ANFITRION, Decimal("0.10"))
        self.assertEqual(Decimal("1") - PREMIO_CON_ANFITRION - COMISION_ANFITRION,
                         Decimal("0.20"))
        # Sala de trabajo: 80 % al ganador, 15 % al anfitrión y 5 % para la app.
        self.assertEqual(PREMIO_TRABAJO, Decimal("0.80"))
        self.assertEqual(COMISION_TRABAJO, Decimal("0.15"))
        self.assertEqual(Decimal("1") - PREMIO_TRABAJO - COMISION_TRABAJO, Decimal("0.05"))


class RepartoEventoTest(unittest.TestCase):
    """El reparto por porcentaje de la sala de eventos: 1º, 2º y 3º."""

    def test_reparte_60_15_5_del_bote(self):
        r = reparto_evento(10_000, (60, 15, 5))
        self.assertEqual(r["premios"], [6_000, 1_500, 500])
        self.assertEqual(r["app"], 2_000)

    def test_nunca_pierde_un_centimo(self):
        for bote in range(0, 20_000):
            r = reparto_evento(bote, (60, 15, 5))
            self.assertEqual(sum(r["premios"]) + r["app"], bote,
                             f"no cuadra con bote {bote}")

    def test_cada_puesto_trunca_al_centimo_y_la_casa_se_queda_el_resto(self):
        r = reparto_evento(101, (60, 15, 5))
        self.assertEqual(r["premios"], [60, 15, 5])
        self.assertEqual(r["app"], 21)

    def test_la_app_nunca_pierde_dinero(self):
        for bote in range(0, 20_000):
            self.assertGreaterEqual(reparto_evento(bote, (60, 15, 5))["app"], 0)

    def test_porcentajes_mayores_de_100_se_rechazan(self):
        with self.assertRaises(ErrorDeSalas):
            reparto_evento(10_000, (80, 30, 10))

    def test_bote_o_porcentaje_invalidos_se_rechazan(self):
        with self.assertRaises(ErrorDeSalas):
            reparto_evento(-1, (60, 15, 5))
        with self.assertRaises(ErrorDeSalas):
            reparto_evento(10.5, (60, 15, 5))
        with self.assertRaises(ErrorDeSalas):
            reparto_evento(10_000, ())
        with self.assertRaises(ErrorDeSalas):
            reparto_evento(10_000, (60, -1, 5))

class RepartoPorPuestosTest(unittest.TestCase):
    """El reparto de una sala de jugador que premia 1º, 2º y 3º."""

    def test_reparte_los_tres_puestos_y_deja_la_comision_y_la_app(self):
        r = reparto_por_puestos(10_000, (50, 15, 5), con_anfitrion=True, comision_pct=10)
        self.assertEqual(r["premios"], [5_000, 1_500, 500])
        self.assertEqual(r["anfitrion"], 1_000)
        self.assertEqual(r["app"], 2_000)

    def test_sin_anfitrion_la_app_se_queda_lo_que_sobra(self):
        r = reparto_por_puestos(10_000, (50, 15, 5))
        self.assertEqual(r["premios"], [5_000, 1_500, 500])
        self.assertEqual(r["anfitrion"], 0)
        self.assertEqual(r["app"], 3_000)

    def test_nunca_pierde_un_centimo(self):
        for bote in range(0, 20_000):
            r = reparto_por_puestos(bote, (50, 15, 5), con_anfitrion=True, comision_pct=10)
            self.assertEqual(sum(r["premios"]) + r["anfitrion"] + r["app"], bote,
                             f"no cuadra con bote {bote}")

    def test_los_premios_mas_la_comision_no_pasan_de_100(self):
        with self.assertRaises(ErrorDeSalas):
            reparto_por_puestos(10_000, (60, 15, 5), con_anfitrion=True, comision_pct=30)


class SalaVariosPuestosTest(unittest.TestCase):
    """Un anfitrión crea su sala con uno o con tres puestos premiados."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)

    def test_una_sala_nueva_premia_un_solo_puesto(self):
        s = self.salas.crear("ana@correo.com", "La de Ana", "normal", "10,00")
        self.assertEqual(s.plazas, 1)
        self.assertFalse(s.reparte_varios_puestos)
        r = s.reparto(10_000)
        self.assertEqual(r["premio"], 7_000)
        self.assertEqual(r["anfitrion"], 1_000)
        self.assertEqual(r["app"], 2_000)

    def test_una_sala_de_tres_puestos_reparte_50_15_5(self):
        s = self.salas.crear("ana@correo.com", "Tres premios", "normal", "10,00",
                             puestos=3)
        self.assertEqual(s.plazas, 3)
        self.assertTrue(s.reparte_varios_puestos)
        r = s.reparto(10_000)
        self.assertEqual(r["premios"], [5_000, 1_500, 500])
        self.assertEqual(r["anfitrion"], 1_000)
        self.assertEqual(r["app"], 2_000)

    def test_los_porcentajes_se_pueden_elegir(self):
        s = self.salas.crear("ana@correo.com", "A mi gusto", "normal", "10,00",
                             puestos=3, premios_pct="40,20,10")
        self.assertEqual(list(s.premios_pct), [40, 20, 10])
        r = s.reparto(10_000)
        self.assertEqual(r["premios"], [4_000, 2_000, 1_000])

    def test_los_premios_no_pueden_pasarse_del_70(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Cara", "normal", "10,00",
                             puestos=3, premios_pct="60,20,10")

    def test_puestos_inventados_se_rechazan(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Dos", "normal", "10,00", puestos=2)

    def test_faltan_porcentajes_para_los_puestos(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.crear("ana@correo.com", "Corta", "normal", "10,00",
                             puestos=3, premios_pct="50,20")

    def test_los_puestos_sobreviven_al_reinicio(self):
        self.salas.crear("ana@correo.com", "Tres premios", "normal", "10,00", puestos=3)
        otra = Salas(self.almacen)
        self.assertEqual(otra.de_dueno("ana@correo.com")[0].plazas, 3)


class TresPuestosJuegoTest(unittest.TestCase):
    """Una sala de tres puestos paga a los tres y cierra al tercero."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)
        self.monedero = Monedero(self.almacen)
        self.sala = self.salas.crear("ana@correo.com", "Tres premios", "normal",
                                     "10,00", puestos=3)

    def test_tres_ganadores_cobran_su_parte_y_el_anfitrion_una_vez(self):
        from bingo.cartones import patron_cumplido

        bingo = SalaBingo()

        def reparto(pid, bote):
            r = self.salas.de(self.sala.id).reparto(bote)
            r["anfitrion_correo"] = self.sala.dueno
            return r

        mesa = MesaBingo(sala=bingo, monedero=self.monedero, repartidor=reparto)
        partida = bingo.abrir_partida(self.sala.precio_carton / 100, patron="linea_h1",
                                      sala=self.sala.id, plazas=self.sala.plazas)
        jugadores = ["a@correo.com", "b@correo.com", "c@correo.com"]
        cartones = {}
        for j in jugadores:
            self.monedero.recargar(j, 100_000, "prueba")
            cartones[j], _ = mesa.comprar_carton(partida.id, j)
        bingo.empezar(partida.id)
        # Tres cartones a $ 10 = $ 30 = 3.000 céntimos.
        self.assertEqual(partida.precio_carton * len(partida.cartones), 3_000)

        saldos_antes = {j: self.monedero.saldo(j) for j in jugadores}
        anfitrion_antes = self.monedero.saldo("ana@correo.com")
        pagados = {}
        for j in jugadores:
            while not patron_cumplido(partida.cartones[cartones[j]], "linea_h1"):
                bingo.sacar_bola(partida.id)
            res = mesa.resolver_cantada(partida.id, j, cartones[j])
            pagados[j] = res["premio"]

        # 50 % de 3.000 = 1.500, 15 % = 450, 5 % = 150.
        self.assertEqual(pagados["a@correo.com"], 1_500)
        self.assertEqual(pagados["b@correo.com"], 450)
        self.assertEqual(pagados["c@correo.com"], 150)
        self.assertEqual(self.monedero.saldo("a@correo.com") - saldos_antes["a@correo.com"], 1_500)
        self.assertEqual(self.monedero.saldo("b@correo.com") - saldos_antes["b@correo.com"], 450)
        self.assertEqual(self.monedero.saldo("c@correo.com") - saldos_antes["c@correo.com"], 150)
        # El anfitrión cobra su 10 % una sola vez, no tres.
        self.assertEqual(self.monedero.saldo("ana@correo.com") - anfitrion_antes, 300)
        self.assertEqual(partida.estado, "terminada")

    def test_la_sala_de_un_puesto_no_cambia(self):
        s = self.salas.crear("ana@correo.com", "De siempre", "normal", "10,00")
        r = s.reparto(10_000)
        self.assertEqual(r["premio"], 7_000)
        self.assertNotIn("premios", r)


class EventoTest(unittest.TestCase):
    """La sala de eventos Lago de Maracaibo: aforo, precio y premios."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)

    def test_se_configura_el_precio_el_aforo_y_los_premios(self):
        sala = self.salas.configurar_evento(precio="100,00", aforo=30, premios_pct="70,20,10")
        self.assertEqual(sala.precio_carton, 10_000)
        self.assertEqual(sala.aforo, 30)
        self.assertEqual(list(sala.premios_pct), [70, 20, 10])

    def test_los_porcentajes_pueden_venir_en_texto(self):
        sala = self.salas.configurar_evento(premios_pct="50, 30, 20")
        self.assertEqual(list(sala.premios_pct), [50, 30, 20])

    def test_porcentajes_que_pasan_de_100_se_rechazan(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_evento(premios_pct="80,30,10")

    def test_aforo_negativo_o_desmedido_se_rechaza(self):
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_evento(aforo=-1)
        with self.assertRaises(ErrorDeSalas):
            self.salas.configurar_evento(aforo=99999)

    def test_la_configuracion_sobrevive_al_reinicio(self):
        self.salas.configurar_evento(precio="200,00", aforo=10)
        otra = Salas(self.almacen)
        self.assertEqual(otra.evento().precio_carton, 20_000)
        self.assertEqual(otra.evento().aforo, 10)

    def test_la_sala_de_evento_no_es_de_la_casa_ni_de_un_jugador(self):
        self.assertNotIn(self.salas.evento(), self.salas.de_la_casa())
        self.assertFalse(self.salas.evento().es_de_jugador)


class EventoJuegoTest(unittest.TestCase):
    """Una partida de evento reparte los tres puestos por porcentaje."""

    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.salas = Salas(self.almacen)
        self.monedero = Monedero(self.almacen)

    def test_tres_ganadores_cobran_su_porcentaje(self):
        from bingo.cartones import patron_cumplido

        evento = self.salas.evento()  # 60/15/5, Bs 50 el cartón
        bingo = SalaBingo()

        def reparto(pid, bote):
            return self.salas.de(evento.id).reparto(bote)

        mesa = MesaBingo(sala=bingo, monedero=self.monedero, repartidor=reparto)
        partida = bingo.abrir_partida(evento.precio_carton / 100, patron="linea_h1",
                                      sala=evento.id, plazas=3)
        jugadores = ["a@correo.com", "b@correo.com", "c@correo.com"]
        cartones = {}
        for j in jugadores:
            self.monedero.recargar(j, 100_000, "prueba")
            cartones[j], _ = mesa.comprar_carton(partida.id, j)
        bingo.empezar(partida.id)
        bote = partida.precio_carton * len(partida.cartones)   # 3 x $ 2 = $ 6
        self.assertEqual(bote, 600)

        pagados = {}
        for j in jugadores:
            while not patron_cumplido(partida.cartones[cartones[j]], "linea_h1"):
                bingo.sacar_bola(partida.id)
            res = mesa.resolver_cantada(partida.id, j, cartones[j])
            pagados[j] = res["premio"]

        # 60% de 600 = 360, 15% = 90, 5% = 30.
        self.assertEqual(pagados["a@correo.com"], 360)
        self.assertEqual(pagados["b@correo.com"], 90)
        self.assertEqual(pagados["c@correo.com"], 30)
        self.assertEqual(partida.estado, "terminada", "con los 3 puestos cubiertos, cierra")

    def test_un_jugador_no_puede_llevarse_dos_puestos(self):
        from bingo.cartones import patron_cumplido

        evento = self.salas.evento()
        bingo = SalaBingo()

        def reparto(pid, bote):
            return self.salas.de(evento.id).reparto(bote)

        mesa = MesaBingo(sala=bingo, monedero=self.monedero, repartidor=reparto)
        partida = bingo.abrir_partida(evento.precio_carton / 100, patron="linea_h1",
                                      sala=evento.id, plazas=3)
        self.monedero.recargar("a@correo.com", 100_000, "prueba")
        c1, _ = mesa.comprar_carton(partida.id, "a@correo.com")
        c2, _ = mesa.comprar_carton(partida.id, "a@correo.com")
        bingo.empezar(partida.id)
        while not patron_cumplido(partida.cartones[c1], "linea_h1"):
            bingo.sacar_bola(partida.id)
        mesa.resolver_cantada(partida.id, "a@correo.com", c1)
        with self.assertRaises(Exception):
            mesa.resolver_cantada(partida.id, "a@correo.com", c2)


if __name__ == "__main__":
    unittest.main()
