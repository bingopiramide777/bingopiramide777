"""Pruebas de las salas y del reparto del dinero.

Esta es la parte donde un error cuesta dinero de verdad, así que se prueban a
fondo los céntimos: que nada se pierda y que nadie cobre de más.
"""

from __future__ import annotations

import unittest

from bingo import MesaBingo, Sala as SalaBingo
from nucleo.almacen import Almacen
from nucleo.monedero import Monedero
from nucleo.money import a_texto
from nucleo.salas import (
    COMISION_ANFITRION,
    PREMIO_CASA,
    ErrorDeSalas,
    Salas,
    reparto_del_bote,
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

    def test_vienen_las_tres_salas_de_la_casa(self):
        nombres = [s.nombre for s in self.salas.todas()]
        self.assertEqual(nombres, ["Dubai", "Roma", "Estelar"])
        self.assertTrue(all(not s.es_de_jugador for s in self.salas.todas()))

    def test_cada_sala_tiene_su_precio_y_su_modo(self):
        dubai, roma, estelar = self.salas.todas()
        self.assertEqual(dubai.precio_carton, 500)
        self.assertEqual(roma.precio_carton, 1_000)
        self.assertEqual(estelar.modo, "carton_lleno")

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
            self.salas.crear("ana@correo.com", "Dubai", "normal", "10,00")

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
            self.monedero.recargar(j, 100_000, "prueba")
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
        res = self._jugar("sala-roma", ["ana@correo.com", "luis@correo.com"])
        # 2 cartones x Bs 10 = Bs 20 de bote
        self.assertEqual(res["bote"], 2_000)
        self.assertEqual(res["premio"], 1_600)
        self.assertEqual(res["anfitrion"], 0)
        self.assertEqual(res["app"], 400)

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
        antes = 100_000 - 1_000
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
        self._jugar("sala-roma", ["ana@correo.com", "luis@correo.com"])
        self._jugar(sala.id, ["ana@correo.com", "luis@correo.com"])
        e = self.salas.economia()
        self.assertEqual(e["partidas"], 2)
        self.assertEqual(e["botes"], 4_000)
        self.assertEqual(e["premios"], 3_200)
        self.assertEqual(e["comisiones"], 200)
        self.assertEqual(e["app"], 600)
        # Y el reparto siempre cuadra.
        self.assertEqual(e["premios"] + e["comisiones"] + e["app"], e["botes"])

    def test_sin_partidas_no_hay_ganancias(self):
        e = self.salas.economia()
        self.assertEqual(e["app"], 0)
        self.assertEqual(e["botes"], 0)
        self.assertEqual(a_texto(e["app"]), "Bs 0,00")

    def test_los_porcentajes_son_los_documentados(self):
        self.assertEqual(PREMIO_CASA, COMISION_ANFITRION * 8)


if __name__ == "__main__":
    unittest.main()
