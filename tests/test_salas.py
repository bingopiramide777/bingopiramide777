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
from nucleo.salas import (
    COMISION_ANFITRION,
    PREMIO_CASA,
    SALA_CASA_ID,
    SALA_CASA_NOMBRE,
    SALAS_INICIALES_ANTIGUAS,
    ErrorDeSalas,
    Salas,
    reparto_del_bote,
    reparto_evento,
)


class RepartoTest(unittest.TestCase):
    """El reparto del bote: la cuenta más delicada del programa."""

    def test_sala_de_la_casa_gana_80_20(self):
        r = reparto_del_bote(10_000, con_anfitrion=False)
        self.assertEqual(r["premio"], 8_000)
        self.assertEqual(r["anfitrion"], 0)
        self.assertEqual(r["app"], 2_000)

    def test_sala_de_jugador_el_ganador_cobra_lo_mismo(self):
        r = reparto_del_bote(10_000, con_anfitrion=True)
        self.assertEqual(r["premio"], 8_000, "el ganador no cobra menos por jugar en sala ajena")
        self.assertEqual(r["anfitrion"], 1_000)
        self.assertEqual(r["app"], 1_000)

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
                                   "Nueva Esparta", SALA_CASA_NOMBRE])
        self.assertTrue(all(not s.es_de_jugador for s in self.salas.de_la_casa()))

    def test_viene_la_sala_de_jugar_desde_casa(self):
        """La sala para trabajar desde casa: cartón lleno y 6 cartones por jugador."""
        sala = self.salas.de(SALA_CASA_ID)
        self.assertEqual(sala.nombre, SALA_CASA_NOMBRE)
        self.assertEqual(sala.modo, "carton_lleno")
        self.assertEqual(sala.tipo_juego, "carton_lleno")
        self.assertEqual(sala.precio_carton, 50_00)
        self.assertEqual(sala.max_cartones, 6)
        self.assertFalse(sala.es_de_jugador)

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
            "Zulia": 2_000_00,
            "Lara": 1_000_00,
            "Carabobo": 500_00,
            "Mérida": 200_00,
            "Táchira": 100_00,
            "Nueva Esparta": 50_00,
            SALA_CASA_NOMBRE: 50_00,
        })
        modos = {s.nombre: s.modo for s in self.salas.de_la_casa()}
        self.assertEqual(modos["Carabobo"], "carton_lleno")
        self.assertEqual(modos["Lara"], "competencia")

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
        """Bs 2.000 no cabe en el tope de las salas de jugador, pero sí aquí."""
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


class MigracionPreciosTest(unittest.TestCase):
    """Bases de datos viejas: los precios suben una vez, sin pisar al admin."""

    def test_los_precios_viejos_se_actualizan(self):
        almacen = Almacen(":memory:")
        # Una base como la de antes: precios bajos y la sala llamada Miranda.
        for id_, viejo in SALAS_INICIALES_ANTIGUAS.items():
            almacen.guardar_sala({
                "id": id_, "nombre": "Miranda" if id_ == "sala-miranda" else id_,
                "modo": "normal", "precio_carton": viejo, "dueno": "", "publica": 1,
                "creada": 0.0, "activa": 1, "es_evento": 0, "aforo": 0, "premios_pct": "",
            })
        salas = Salas(almacen)
        self.assertEqual(salas.de("sala-zulia").precio_carton, 2_000_00)
        self.assertEqual(salas.de("sala-tachira").precio_carton, 100_00)
        self.assertEqual(salas.de("sala-miranda").nombre, "Mérida")
        self.assertEqual(salas.de("sala-miranda").precio_carton, 200_00)

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
        # 2 cartones x Bs 1.000 = Bs 2.000 de bote
        self.assertEqual(res["bote"], 200_000)
        self.assertEqual(res["premio"], 160_000)
        self.assertEqual(res["anfitrion"], 0)
        self.assertEqual(res["app"], 40_000)

    def test_sala_de_jugador_paga_al_anfitrion(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        res = self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        self.assertEqual(res["bote"], 2_000)
        self.assertEqual(res["premio"], 1_600)
        self.assertEqual(res["anfitrion"], 200)
        self.assertEqual(res["app"], 200)

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
        self.assertEqual(g["anfitrion"], 400)
        self.assertEqual(g["app"], 400)

    def test_la_economia_suma_todas_las_salas(self):
        sala = self.salas.crear("duena@correo.com", "La de la dueña", "normal", "10,00")
        self._jugar("sala-lara", ["ana@correo.com", "luis@correo.com"])
        self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        e = self.salas.economia()
        self.assertEqual(e["partidas"], 2)
        # Lara (Bs 1.000 el cartón) + la sala de la dueña (Bs 10): 202.000 céntimos.
        self.assertEqual(e["botes"], 202_000)
        self.assertEqual(e["premios"], 161_600)
        self.assertEqual(e["comisiones"], 200)
        self.assertEqual(e["app"], 40_200)
        # Y el reparto siempre cuadra.
        self.assertEqual(e["premios"] + e["comisiones"] + e["app"], e["botes"])

    def test_sin_partidas_no_hay_ganancias(self):
        e = self.salas.economia()
        self.assertEqual(e["app"], 0)
        self.assertEqual(e["botes"], 0)
        self.assertEqual(a_texto(e["app"]), "Bs 0,00")

    def test_los_porcentajes_son_los_documentados(self):
        # El ganador siempre cobra el 80 %; el 20 % restante se reparte a partes
        # iguales entre el anfitrión (10 %) y la app (10 %).
        self.assertEqual(PREMIO_CASA, Decimal("0.80"))
        self.assertEqual(COMISION_ANFITRION, Decimal("0.10"))
        self.assertEqual(Decimal("1") - PREMIO_CASA - COMISION_ANFITRION, Decimal("0.10"))


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
        bote = partida.precio_carton * len(partida.cartones)   # 3 x Bs 50 = Bs 150
        self.assertEqual(bote, 15_000)

        pagados = {}
        for j in jugadores:
            while not patron_cumplido(partida.cartones[cartones[j]], "linea_h1"):
                bingo.sacar_bola(partida.id)
            res = mesa.resolver_cantada(partida.id, j, cartones[j])
            pagados[j] = res["premio"]

        # 60% de 15.000 = 9.000, 15% = 2.250, 5% = 750.
        self.assertEqual(pagados["a@correo.com"], 9_000)
        self.assertEqual(pagados["b@correo.com"], 2_250)
        self.assertEqual(pagados["c@correo.com"], 750)
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
