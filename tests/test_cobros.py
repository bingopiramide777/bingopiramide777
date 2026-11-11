"""Pruebas del sistema de cobro: los dos 20 % y la auditoría anti-duplicados."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest

from bingo.cartones import PATRONES
from nucleo import Almacen
from nucleo.cobros import Cobros
from nucleo.depositos import Depositos
from nucleo.monedero import Monedero
from nucleo.salas import SALA_CASA_ID, Salas
from web.servidor import Juego

ADMIN = "bingopiramide777@gmail.com"
CLAVE = "ClaveAdmin777"


class CobrosTest(unittest.TestCase):
    def setUp(self):
        self.almacen = Almacen(os.path.join(tempfile.mkdtemp(), "cobros.db"))
        self.juego = Juego(almacen=self.almacen, correo_admin=ADMIN, clave_admin=CLAVE)

    def tearDown(self):
        self.almacen.cerrar()

    def _jugador(self, correo="j@x.com", recarga=100_00):
        self.juego.usuarios.registrar(correo, "miClaveSegura1", "Ana", "jugador")
        if recarga:
            self.juego.monedero.recargar(correo, recarga, "prueba")
        return correo

    def _bingo(self, sala_id, correo, n=5):
        partida = self.juego.partida(sala_id)
        ids = []
        for _ in range(n):
            cid, _ = self.juego.mesa.comprar_carton(partida.id, correo)
            ids.append(cid)
            self.juego.guardar_carton(partida, cid)
        self.juego._guardar(partida)
        self.juego.mesa.sala.empezar(partida.id)
        with self.juego.candado:
            p = self.juego.mesa.sala.partidas[partida.id]
            p.cartones[ids[0]].marcados |= PATRONES[p.patron]
        res = self.juego.mesa.resolver_cantada(partida.id, correo, ids[0])
        self.juego._guardar(partida)
        return res

    # -- el 20 % del depósito se cobra UNA vez --

    def test_el_20_por_ciento_del_deposito_se_cobra_una_sola_vez(self):
        self._jugador(recarga=0)
        d = self.juego.depositos.declarar(
            "j@x.com", "20,00", "REF1", "", datetime.date.today().isoformat(), "paypal", "")
        d = self.juego.depositos.acreditar(d.id, ADMIN, "ok")
        self.assertEqual(d.comision, 400)      # 20 % de 20,00
        self.assertEqual(d.acreditado, 1600)
        # Reintentar acreditar el mismo depósito no vuelve a cobrar.
        with self.assertRaises(Exception):
            self.juego.depositos.acreditar(d.id, ADMIN, "ok")
        self.assertEqual(self.juego.monedero.saldo("j@x.com"), 1600)

    # -- la sala de trabajo deja el 20 % al dueño (15 + 5) --

    def test_la_sala_de_trabajo_deja_20_al_dueno(self):
        correo = self._jugador()
        res = self._bingo(SALA_CASA_ID, correo, n=5)
        bote = res["bote"]
        self.assertEqual(res["premio"], bote * 80 // 100)   # 80 % al ganador
        self.assertEqual(res["anfitrion"], bote * 15 // 100)  # 15 % al anfitrión
        # El 5 % que queda a la app va a la misma cuenta (el dueño es la admin),
        # así que el dueño de la sala se queda, de hecho, el 20 % del bote.
        self.assertEqual(res["app"] + res["anfitrion"], bote * 20 // 100)
        self.assertEqual(res["app"], bote * 5 // 100)
        self.assertEqual(self.juego.monedero.saldo(ADMIN), bote * 15 // 100)

    def test_las_otras_salas_no_cambian(self):
        correo = self._jugador()
        res = self._bingo("sala-zulia", correo, n=5)  # sala de la casa
        bote = res["bote"]
        self.assertEqual(res["anfitrion"], 0)
        self.assertEqual(res["premio"], bote * 80 // 100)
        self.assertEqual(res["app"], bote * 20 // 100)

    def test_la_sala_normal_reparte_70_10_20(self):
        # La app ya cobró su 20 % anticipado en el depósito, pero del bote de una
        # sala de jugador también se queda el 20 %: el ganador el 70 %, el dueño
        # de la mesa el 10 %.
        dueno = self._jugador("dueno@x.com", recarga=0)
        jugador = self._jugador("jug@x.com")
        sala = self.juego.salas.crear(dueno, "La del barrio", "normal", "10,00")
        res = self._bingo(sala.id, jugador, n=5)
        bote = res["bote"]
        self.assertEqual(res["premio"], bote * 70 // 100)
        self.assertEqual(res["anfitrion"], bote * 10 // 100)
        self.assertEqual(res["app"], bote * 20 // 100)
        self.assertEqual(self.juego.monedero.saldo(dueno), bote * 10 // 100)

    # -- auditoría --

    def test_la_auditoria_no_ve_duplicados_en_un_flujo_limpio(self):
        self._jugador()
        self._bingo(SALA_CASA_ID, "j@x.com", n=3)
        a = self.juego.cobros.auditar()
        self.assertTrue(a["sin_duplicados"])
        self.assertEqual(a["avisos"], [])

    def test_la_base_impide_el_mismo_deposito_dos_veces(self):
        # La clave única (referencia, dia) hace imposible registrar dos veces el
        # mismo pago: la auditoría no debería encontrar nada aunque se intente.
        self._jugador(recarga=0)
        hoy = datetime.date.today().isoformat()
        d = self.juego.depositos.declarar("j@x.com", "20,00", "REF9", "", hoy, "paypal", "")
        self.juego.depositos.acreditar(d.id, ADMIN, "ok")
        with self.assertRaises(Exception):
            self.juego.depositos.declarar("j@x.com", "20,00", "REF9", "", hoy, "paypal", "")
        self.assertTrue(self.juego.cobros.auditar()["sin_duplicados"])

    def test_la_auditoria_pillaria_una_comision_de_sala_pagada_dos_veces(self):
        # Si por un fallo se pagase dos veces la comisión de la misma partida,
        # la auditoría tiene que verlo. Se duplica el movimiento real que dejó
        # el bingo (mismo motivo = misma partida).
        correo = self._jugador()
        self._bingo(SALA_CASA_ID, correo, n=3)
        real = [m for m in self.almacen.movimientos_por_motivo("comisión de sala")
                if m["correo"] == ADMIN]
        self.assertTrue(real)
        self.almacen.aplicar_movimiento(
            ADMIN, "premio", 1, real[0]["motivo"], 1.0, "m-extra")
        a = self.juego.cobros.auditar()
        self.assertFalse(a["sin_duplicados"])
        self.assertTrue(any("comisión(es) de anfitrión" in aviso for aviso in a["avisos"]))


    def test_la_definicion_lista_los_cobros(self):
        claves = {d["clave"] for d in self.juego.cobros.definicion()}
        self.assertEqual(
            claves,
            {"deposito", "anfitrion_trabajo", "app_trabajo", "anfitrion_normal", "padrino"})

    def test_el_resumen_trae_totales_y_auditoria(self):
        self._jugador()
        self._bingo(SALA_CASA_ID, "j@x.com", n=2)
        r = self.juego.cobros.resumen()
        self.assertIn("definicion", r)
        self.assertIn("totales", r)
        self.assertIn("auditoria", r)
        self.assertTrue(r["totales"]["anfitrion_texto"].startswith("🫰"))


if __name__ == "__main__":
    unittest.main()
