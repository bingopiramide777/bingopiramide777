"""Pruebas del bingo: cartones, bombo, sala y mesa. Sin simulacros."""

from __future__ import annotations

import unittest
from decimal import Decimal

from bingo import (
    PATRONES,
    Bombo,
    Carton,
    ErrorDeBingo,
    MesaBingo,
    Sala,
    generar_carton,
    patron_cumplido,
    patrones_cumplidos,
    fichas_que_faltan,
)
from bingo.mesa import ErrorDeMesaBingo
from bingo.sala import ErrorDeSala
from nucleo import Almacen, Monedero


class AzarFijo:
    """Azar de mentira: siempre elige el primer elemento disponible."""

    def randrange(self, n: int) -> int:
        return 0


class CartonTest(unittest.TestCase):
    def test_carton_valido(self):
        c = Carton(
            numeros=(
                (1, 16, 31, 46, 61),
                (2, 17, 32, 47, 62),
                (3, 18, 0, 48, 63),
                (4, 19, 34, 49, 64),
                (5, 20, 35, 50, 65),
            )
        )
        self.assertTrue(c.marcado(2, 2))  # el centro nace libre

    def test_rechaza_rejilla_que_no_es_5x5(self):
        with self.assertRaises(ErrorDeBingo):
            Carton(numeros=((1, 2, 3), (4, 5, 6)))

    def test_rechaza_numero_fuera_de_su_columna(self):
        with self.assertRaises(ErrorDeBingo):
            Carton(
                numeros=(
                    (16, 16, 31, 46, 61),  # 16 no cabe en la columna B
                    (2, 17, 32, 47, 62),
                    (3, 18, 0, 48, 63),
                    (4, 19, 34, 49, 64),
                    (5, 20, 35, 50, 65),
                )
            )

    def test_marcar_solo_marca_lo_que_esta(self):
        c = generar_carton(generador=AzarFijo())
        numero = c.numeros[0][0]
        self.assertTrue(c.marcar(numero))
        self.assertFalse(c.marcar(numero))       # ya estaba
        self.assertFalse(c.marcar(999))          # no está

    def test_generar_carton_cumple_los_rangos(self):
        for _ in range(30):
            c = generar_carton()
            for col, (lo, hi) in enumerate(((1, 15), (16, 30), (31, 45), (46, 60), (61, 75))):
                for fila in range(5):
                    if (fila, col) == (2, 2):
                        continue
                    self.assertTrue(lo <= c.numeros[fila][col] <= hi)


class PatronTest(unittest.TestCase):
    def setUp(self):
        self.c = Carton(
            numeros=(
                (1, 16, 31, 46, 61),
                (2, 17, 32, 47, 62),
                (3, 18, 0, 48, 63),
                (4, 19, 34, 49, 64),
                (5, 20, 35, 50, 65),
            )
        )

    def test_linea_horizontal_solo_con_la_fila_completa(self):
        self.assertFalse(patron_cumplido(self.c, "linea_h1"))
        for n in (1, 16, 31, 46):
            self.c.marcar(n)
        self.assertFalse(patron_cumplido(self.c, "linea_h1"))
        self.c.marcar(61)
        self.assertTrue(patron_cumplido(self.c, "linea_h1"))

    def test_el_centro_libre_cuenta_para_la_fila_del_medio(self):
        for n in (3, 18, 48, 63):   # fila 3, sin el centro
            self.c.marcar(n)
        self.assertTrue(patron_cumplido(self.c, "linea_h3"))

    def test_carton_lleno_necesita_todo(self):
        for fila in range(5):
            for col in range(5):
                self.c.marcar(self.c.numeros[fila][col])
        self.assertIn("carton_lleno", patrones_cumplidos(self.c))

    def test_patron_que_no_existe(self):
        with self.assertRaises(ErrorDeBingo):
            patron_cumplido(self.c, "patron_inventado")

    def test_hay_patrones_esperados(self):
        for nombre in ("linea_h1", "linea_v5", "diagonal", "esquinas", "carton_lleno"):
            self.assertIn(nombre, PATRONES)


class BomboTest(unittest.TestCase):
    def test_saca_las_75_sin_repetir(self):
        b = Bombo()
        sacadas = [b.sacar() for _ in range(75)]
        self.assertEqual(sorted(sacadas), list(range(1, 76)))
        self.assertEqual(len(set(sacadas)), 75)

    def test_no_se_puede_sacar_mas_de_75(self):
        b = Bombo()
        for _ in range(75):
            b.sacar()
        self.assertEqual(b.quedan(), 0)
        with self.assertRaises(ErrorDeBingo):
            b.sacar()


class SalaTest(unittest.TestCase):
    def setUp(self):
        self.sala = Sala()

    def test_abrir_partida_y_vender_cartones(self):
        p = self.sala.abrir_partida("10.00")
        self.assertTrue(p.abierta)
        carton, precio = self.sala.comprar_carton(p.id, "ana@correo.com")
        self.assertEqual(precio, 1_000)
        self.assertIn(carton.id, p.cartones)
        self.assertEqual(p.dueno[carton.id], "ana@correo.com")

    def test_no_se_venden_cartones_con_la_partida_empezada(self):
        p = self.sala.abrir_partida("10.00")
        self.sala.comprar_carton(p.id, "ana@correo.com")
        self.sala.empezar(p.id)
        with self.assertRaises(ErrorDeSala):
            self.sala.comprar_carton(p.id, "luis@correo.com")

    def test_no_empieza_sin_cartones(self):
        p = self.sala.abrir_partida("10.00")
        with self.assertRaises(ErrorDeSala):
            self.sala.empezar(p.id)

    def test_precio_de_carton_debe_ser_positivo(self):
        with self.assertRaises((ErrorDeSala, ValueError)):
            self.sala.abrir_partida("0")

    def test_patron_que_no_existe(self):
        with self.assertRaises(ErrorDeSala):
            self.sala.abrir_partida("10.00", patron="no_existe")

    def test_sacar_bola_marca_los_cartones(self):
        p = self.sala.abrir_partida("10.00")
        carton, _ = self.sala.comprar_carton(p.id, "ana@correo.com")
        self.sala.empezar(p.id)
        bola = self.sala.sacar_bola(p.id)
        # La bola sacada, si está en el cartón, queda marcada.
        en_carton = any(bola == carton.numeros[f][c] for f in range(5) for c in range(5))
        if en_carton:
            self.assertTrue(any(carton.marcado(f, c) for f in range(5) for c in range(5)))

    def test_cantar_en_falso_no_vale(self):
        p = self.sala.abrir_partida("10.00")
        carton, _ = self.sala.comprar_carton(p.id, "ana@correo.com")
        self.sala.empezar(p.id)
        self.sala.sacar_bola(p.id)
        with self.assertRaises(ErrorDeSala):
            self.sala.cantar(p.id, "ana@correo.com", carton.id)

    def test_no_se_canta_con_carton_de_otro(self):
        p = self.sala.abrir_partida("10.00")
        carton, _ = self.sala.comprar_carton(p.id, "ana@correo.com")
        self.sala.empezar(p.id)
        with self.assertRaises(ErrorDeSala):
            self.sala.cantar(p.id, "luis@correo.com", carton.id)

    def test_cantada_valida_termina_la_partida(self):
        p = self.sala.abrir_partida("10.00", patron="linea_h1")
        carton, _ = self.sala.comprar_carton(p.id, "ana@correo.com")
        # Marcamos a mano la fila 1 completa, como si hubieran salido las bolas.
        for col in range(5):
            carton.marcar(carton.numeros[0][col])
        self.sala.empezar(p.id)
        res = self.sala.cantar(p.id, "ana@correo.com", carton.id)
        self.assertEqual(res["ganador"], "ana@correo.com")
        self.assertEqual(p.estado, "terminada")

    def test_bote_es_el_precio_por_los_cartones(self):
        p = self.sala.abrir_partida("10.00")
        for _ in range(3):
            self.sala.comprar_carton(p.id, "ana@correo.com")
        self.assertEqual(self.sala.bote(p.id), 3_000)


class MesaBingoTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(":memory:")
        self.mesa = MesaBingo(sala=Sala(), monedero=Monedero(self.almacen), reparto=Decimal("0.80"))
        self.partida = self.mesa.sala.abrir_partida("10.00", patron="linea_h1")

    def tearDown(self):
        self.almacen.cerrar()

    def test_comprar_carton_cobra(self):
        self.mesa.monedero.recargar("ana@correo.com", 10_000)
        self.mesa.comprar_carton(self.partida.id, "ana@correo.com")
        self.assertEqual(self.mesa.monedero.saldo("ana@correo.com"), 9_000)

    def test_sin_saldo_no_hay_carton_ni_cobro(self):
        with self.assertRaises(ErrorDeMesaBingo):
            self.mesa.comprar_carton(self.partida.id, "ana@correo.com")
        self.assertEqual(self.mesa.monedero.saldo("ana@correo.com"), 0)
        self.assertEqual(len(self.partida.cartones), 0)   # no quedó colgado

    def test_el_premio_es_el_reparto_del_bote(self):
        self.mesa.monedero.recargar("ana@correo.com", 100_000)
        for _ in range(5):
            self.mesa.comprar_carton(self.partida.id, "ana@correo.com")
        self.assertEqual(self.mesa.sala.bote(self.partida.id), 5_000)
        self.assertEqual(self.mesa.premio_de(self.partida.id), 4_000)  # 80 %

    def test_cantada_valida_paga_el_premio(self):
        self.mesa.monedero.recargar("ana@correo.com", 100_000)
        carton_id, _ = self.mesa.comprar_carton(self.partida.id, "ana@correo.com")
        carton = self.partida.cartones[carton_id]
        for col in range(5):
            carton.marcar(carton.numeros[0][col])
        self.mesa.sala.empezar(self.partida.id)
        antes = self.mesa.monedero.saldo("ana@correo.com")
        res = self.mesa.resolver_cantada(self.partida.id, "ana@correo.com", carton_id)
        self.assertEqual(res["premio"], 800)   # bote 1000 * 0,80
        self.assertEqual(self.mesa.monedero.saldo("ana@correo.com"), antes + 800)

    def test_no_se_paga_dos_veces(self):
        self.mesa.monedero.recargar("ana@correo.com", 100_000)
        carton_id, _ = self.mesa.comprar_carton(self.partida.id, "ana@correo.com")
        carton = self.partida.cartones[carton_id]
        for col in range(5):
            carton.marcar(carton.numeros[0][col])
        self.mesa.sala.empezar(self.partida.id)
        self.mesa.resolver_cantada(self.partida.id, "ana@correo.com", carton_id)
        saldo = self.mesa.monedero.saldo("ana@correo.com")
        with self.assertRaises(ErrorDeSala):
            self.mesa.resolver_cantada(self.partida.id, "ana@correo.com", carton_id)
        self.assertEqual(self.mesa.monedero.saldo("ana@correo.com"), saldo)

    def test_vista_publica_no_expone_datos_privados(self):
        self.mesa.monedero.recargar("ana@correo.com", 10_000)
        self.mesa.comprar_carton(self.partida.id, "ana@correo.com")
        vista = self.mesa.partida_publica(self.partida.id)
        self.assertEqual(set(vista), {"id", "sala", "patron", "tipo_juego", "tipo_juego_texto",
                                      "estado", "precio_carton",
                                      "cartones", "jugadores", "bolas_sacadas", "ganador",
                                      "plazas", "ganadores", "a_cuanto_estan"})
        # La transparencia solo dice a cuánto está cada uno: ni números ni cartones.
        for fila in vista["a_cuanto_estan"]:
            self.assertEqual(set(fila), {"jugador", "cartones", "faltan"})


class TransparenciaTest(unittest.TestCase):
    """Cuántas fichas faltan: la transparencia en vivo del juego."""

    def _carton(self):
        # numeros[fila][col], con cada columna en su rango (B 1-15 … O 61-75).
        numeros = tuple(tuple(col * 15 + 1 + fila for col in range(5)) for fila in range(5))
        return Carton(numeros)

    def test_linea_completa_no_le_falta_nada(self):
        carton = self._carton()
        for c in range(5):
            carton.marcados.add((0, c))
        self.assertEqual(fichas_que_faltan(carton, ("linea_h1",)), 0)

    def test_una_linea_a_medias(self):
        carton = self._carton()
        for c in range(3):
            carton.marcados.add((0, c))
        self.assertEqual(fichas_que_faltan(carton, ("linea_h1",)), 2)

    def test_coge_el_patron_mas_cercano(self):
        carton = self._carton()
        # Tres casillas de la fila 0 y cuatro de la fila 1: la más cerca es la fila 1.
        for c in range(3):
            carton.marcados.add((0, c))
        for c in range(4):
            carton.marcados.add((1, c))
        self.assertEqual(fichas_que_faltan(carton, ("linea_h1", "linea_h2")), 1)

    def test_carton_lleno_cuenta_todas_las_casillas(self):
        carton = self._carton()
        self.assertEqual(fichas_que_faltan(carton, ("carton_lleno",)), 24)  # el centro va libre

    def test_un_patron_que_no_existe_avisa(self):
        with self.assertRaises(ErrorDeBingo):
            fichas_que_faltan(self._carton(), ("inventado",))

    def test_la_mesa_dice_a_cuanto_esta_cada_jugador(self):
        almacen = Almacen(":memory:")
        self.addCleanup(almacen.cerrar)
        mesa = MesaBingo(sala=Sala(), monedero=Monedero(almacen))
        partida = mesa.sala.abrir_partida("10.00", patron="linea_h1")
        for nombre in ("ana@correo.com", "luis@correo.com"):
            mesa.monedero.recargar(nombre, 10_000)
            mesa.comprar_carton(partida.id, nombre)
        filas = mesa.a_cuanto_estan(partida.id)
        self.assertEqual(len(filas), 2)
        for fila in filas:
            self.assertIn(fila["faltan"], range(0, 26))
        # Ordenado: el que va más adelante, primero.
        self.assertEqual(filas, sorted(filas, key=lambda f: f["faltan"]))


if __name__ == "__main__":
    unittest.main()
