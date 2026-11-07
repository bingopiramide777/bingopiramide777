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
)
from bingo.mesa import ErrorDeMesaBingo
from bingo.sala import ErrorDeSala
from nucleo.monedero import ErrorDeMonedero, Monedero


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
        carton, precio = self.sala.comprar_carton(p.id, "ana")
        self.assertEqual(precio, 1_000)
        self.assertIn(carton.id, p.cartones)
        self.assertEqual(p.dueno[carton.id], "ana")

    def test_no_se_venden_cartones_con_la_partida_empezada(self):
        p = self.sala.abrir_partida("10.00")
        self.sala.comprar_carton(p.id, "ana")
        self.sala.empezar(p.id)
        with self.assertRaises(ErrorDeSala):
            self.sala.comprar_carton(p.id, "luis")

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
        carton, _ = self.sala.comprar_carton(p.id, "ana")
        self.sala.empezar(p.id)
        bola = self.sala.sacar_bola(p.id)
        # La bola sacada, si está en el cartón, queda marcada.
        en_carton = any(bola == carton.numeros[f][c] for f in range(5) for c in range(5))
        if en_carton:
            self.assertTrue(any(carton.marcado(f, c) for f in range(5) for c in range(5)))

    def test_cantar_en_falso_no_vale(self):
        p = self.sala.abrir_partida("10.00")
        carton, _ = self.sala.comprar_carton(p.id, "ana")
        self.sala.empezar(p.id)
        self.sala.sacar_bola(p.id)
        with self.assertRaises(ErrorDeSala):
            self.sala.cantar(p.id, "ana", carton.id)

    def test_no_se_canta_con_carton_de_otro(self):
        p = self.sala.abrir_partida("10.00")
        carton, _ = self.sala.comprar_carton(p.id, "ana")
        self.sala.empezar(p.id)
        with self.assertRaises(ErrorDeSala):
            self.sala.cantar(p.id, "luis", carton.id)

    def test_cantada_valida_termina_la_partida(self):
        p = self.sala.abrir_partida("10.00", patron="linea_h1")
        carton, _ = self.sala.comprar_carton(p.id, "ana")
        # Marcamos a mano la fila 1 completa, como si hubieran salido las bolas.
        for col in range(5):
            carton.marcar(carton.numeros[0][col])
        self.sala.empezar(p.id)
        res = self.sala.cantar(p.id, "ana", carton.id)
        self.assertEqual(res["ganador"], "ana")
        self.assertEqual(p.estado, "terminada")

    def test_bote_es_el_precio_por_los_cartones(self):
        p = self.sala.abrir_partida("10.00")
        for _ in range(3):
            self.sala.comprar_carton(p.id, "ana")
        self.assertEqual(self.sala.bote(p.id), 3_000)


class MesaBingoTest(unittest.TestCase):
    def setUp(self):
        self.mesa = MesaBingo(sala=Sala(), monedero=Monedero(), reparto=Decimal("0.80"))
        self.partida = self.mesa.sala.abrir_partida("10.00", patron="linea_h1")

    def test_comprar_carton_cobra(self):
        self.mesa.monedero.recargar("ana", 10_000)
        self.mesa.comprar_carton(self.partida.id, "ana")
        self.assertEqual(self.mesa.monedero.saldo("ana"), 9_000)

    def test_sin_saldo_no_hay_carton_ni_cobro(self):
        with self.assertRaises(ErrorDeMesaBingo):
            self.mesa.comprar_carton(self.partida.id, "ana")
        self.assertEqual(self.mesa.monedero.saldo("ana"), 0)
        self.assertEqual(len(self.partida.cartones), 0)   # no quedó colgado

    def test_el_premio_es_el_reparto_del_bote(self):
        self.mesa.monedero.recargar("ana", 100_000)
        for _ in range(5):
            self.mesa.comprar_carton(self.partida.id, "ana")
        self.assertEqual(self.mesa.sala.bote(self.partida.id), 5_000)
        self.assertEqual(self.mesa.premio_de(self.partida.id), 4_000)  # 80 %

    def test_cantada_valida_paga_el_premio(self):
        self.mesa.monedero.recargar("ana", 100_000)
        carton_id, _ = self.mesa.comprar_carton(self.partida.id, "ana")
        carton = self.partida.cartones[carton_id]
        for col in range(5):
            carton.marcar(carton.numeros[0][col])
        self.mesa.sala.empezar(self.partida.id)
        antes = self.mesa.monedero.saldo("ana")
        res = self.mesa.resolver_cantada(self.partida.id, "ana", carton_id)
        self.assertEqual(res["premio"], 800)   # bote 1000 * 0,80
        self.assertEqual(self.mesa.monedero.saldo("ana"), antes + 800)

    def test_no_se_paga_dos_veces(self):
        self.mesa.monedero.recargar("ana", 100_000)
        carton_id, _ = self.mesa.comprar_carton(self.partida.id, "ana")
        carton = self.partida.cartones[carton_id]
        for col in range(5):
            carton.marcar(carton.numeros[0][col])
        self.mesa.sala.empezar(self.partida.id)
        self.mesa.resolver_cantada(self.partida.id, "ana", carton_id)
        saldo = self.mesa.monedero.saldo("ana")
        with self.assertRaises(ErrorDeSala):
            self.mesa.resolver_cantada(self.partida.id, "ana", carton_id)
        self.assertEqual(self.mesa.monedero.saldo("ana"), saldo)

    def test_vista_publica_no_expone_datos_privados(self):
        self.mesa.monedero.recargar("ana", 10_000)
        self.mesa.comprar_carton(self.partida.id, "ana")
        vista = self.mesa.partida_publica(self.partida.id)
        self.assertEqual(set(vista), {"id", "patron", "estado", "precio_carton",
                                      "cartones", "bolas_sacadas", "ganador"})


if __name__ == "__main__":
    unittest.main()
