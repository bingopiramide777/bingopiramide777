"""Pruebas del catálogo multi-país: países, monedas y métodos de pago."""

from __future__ import annotations

import unittest

from nucleo import paises


class PaisesTest(unittest.TestCase):
    def test_hay_cuatro_paises(self):
        self.assertEqual([p.code for p in paises.PAISES], ["VE", "CO", "CL", "US"])

    def test_cada_pais_tiene_moneda_y_simbolo(self):
        for p in paises.PAISES:
            self.assertTrue(p.moneda)
            self.assertTrue(p.simbolo)
            self.assertTrue(p.locale)

    def test_cada_pais_tiene_su_metodo_de_pago(self):
        for p in paises.PAISES:
            self.assertIsNotNone(paises.metodo_de_pais(p.code),
                                 f"{p.code} no tiene método de pago")

    def test_pais_desconocido_no_revienta(self):
        self.assertIsNone(paises.pais("XX"))
        self.assertFalse(paises.es_pais_valido("XX"))
        # Un país raro cae al de por defecto, no rompe el formateo.
        self.assertEqual(paises.simbolo_de("XX"), "Bs")

    def test_formateo_por_pais(self):
        self.assertEqual(paises.formatear(123450, "VE"), "Bs 1.234,50")
        self.assertEqual(paises.formatear(123450, "CO"), "$ 1.234,50")
        self.assertEqual(paises.formatear(123450, "US"), "$ 1.234,50")

    def test_formateo_negativo(self):
        self.assertEqual(paises.formatear(-500, "VE"), "-Bs 5,00")

    def test_el_pais_activo_manda_en_a_texto(self):
        from nucleo.money import a_texto

        # a_texto convierte de la moneda base a la del país activo. Con la tasa
        # de Chile (0,04), 999.900 céntimos base son 24.997.500 pesos = $ 249.975,00.
        paises.usar_pais("CL")
        try:
            self.assertEqual(a_texto(999900), "$ 249.975,00")
        finally:
            paises.usar_pais("VE")
        # En Venezuela, que es la base, no hay conversión.
        self.assertEqual(a_texto(999900), "Bs 9.999,00")

    def test_venezuela_es_la_moneda_base_y_no_convierte(self):
        self.assertEqual(paises.PAIS_BASE, "VE")
        self.assertEqual(paises.tasa_de("VE"), 1)
        self.assertEqual(paises.a_base(12345, "VE"), 12345)
        self.assertEqual(paises.de_base(12345, "VE"), 12345)

    def test_conversion_de_ida_y_vuelta(self):
        # Un importe en la moneda de cada país, ida y vuelta, no debe descuadrar
        # más de un céntimo por el redondeo.
        for code in ("CO", "CL", "US"):
            with self.subTest(code=code):
                base = paises.a_base(1_000_000, code)
                vuelta = paises.de_base(base, code)
                self.assertLessEqual(abs(vuelta - 1_000_000), 1)

    def test_la_tasa_sale_del_entorno(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_TASA_US": "50"}):
            self.assertEqual(paises.tasa_de("US"), 50)
            # 1.000 céntimos de dólar (10 USD) x 50 = 50.000 céntimos base.
            self.assertEqual(paises.a_base(1_000, "US"), 50_000)

    def test_una_tasa_invalida_cae_en_la_de_defecto(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_TASA_US": "no-es-un-numero"}):
            self.assertEqual(paises.tasa_de("US"), paises.TASAS_POR_DEFECTO["US"])

    def test_formatear_local_usa_la_moneda_del_pais(self):
        # 40.000 céntimos base son Bs 400,00; con tasa 40, son $ 10,00.
        self.assertEqual(paises.formatear_local(40_000, "US"), "$ 10,00")
        self.assertEqual(paises.formatear_local(40_000, "VE"), "Bs 400,00")

    def test_un_pais_invalido_no_cambia_el_activo(self):
        paises.usar_pais("VE")
        elegido = paises.usar_pais("ZZ")
        self.assertEqual(elegido, "VE")
        self.assertEqual(paises.pais_actual(), "VE")

    def test_el_catalogo_trae_todo_lo_que_el_front_necesita(self):
        cat = paises.catalogo()
        self.assertEqual(len(cat["paises"]), 4)
        # EE. UU. tiene dos métodos (Cash App y Wise), así que son 5 en total.
        self.assertEqual(len(cat["metodos_pago"]), 5)
        self.assertEqual(cat["pais_por_defecto"], "VE")
        ve = next(m for m in cat["metodos_pago"] if m["country"] == "VE")
        self.assertEqual(ve["id"], "pago_movil_ve")
        self.assertTrue(ve["platformAccount"])
        self.assertTrue(ve["fields"])

    def test_estados_unidos_ofrece_cash_app_y_wise(self):
        ids = [m.id for m in paises.metodos_de_pais("US")]
        self.assertEqual(ids, ["cashapp_us", "wise_us"])
        # El resto de países sigue con un solo método.
        self.assertEqual([m.id for m in paises.metodos_de_pais("VE")], ["pago_movil_ve"])

    def test_las_cuentas_de_administracion_son_una_por_pais(self):
        cuentas = paises.cuentas_admin()
        self.assertEqual([c.pais for c in cuentas], ["VE", "CO", "CL", "US"])
        # Sin configurar en el entorno, ninguna está lista y todas avisan.
        for c in cuentas:
            self.assertFalse(c.configurada)
            self.assertTrue(c.lineas)
        # Wise de EE. UU. pide tipo de cuenta, número de ruta y número de cuenta.
        us = paises.cuenta_admin("US")
        self.assertEqual([l.label for l in us.lineas],
                         ["Tipo de cuenta", "Número de ruta (para wire y ACH)", "Número de cuenta"])

    def test_la_cuenta_de_administracion_sale_del_entorno(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {
            "BINGO_ADMIN_CUENTA_CO_BANCO": "Nequi",
            "BINGO_ADMIN_CUENTA_CO_DATO1": "3052111153",
            "BINGO_ADMIN_CUENTA_CO_TITULAR": "BingoPiramide777",
        }):
            co = paises.cuenta_admin("CO")
            self.assertTrue(co.configurada)
            self.assertEqual(co.banco, "Nequi")
            valores = [l.valor for l in co.lineas]
            self.assertIn("3052111153", valores)

    def test_la_cuenta_de_venezuela_sale_del_entorno(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_PAGO_TELEFONO": "0412-1111111"}):
            metodo = paises.metodo_de_pais("VE")
            valores = {d.value for d in metodo.platform_account}
        self.assertIn("0412-1111111", valores)

    def test_la_cuenta_de_colombia_sale_del_entorno(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_PAGO_NEQUI_TELEFONO": "3009999999"}):
            metodo = paises.metodo_de_pais("CO")
            valor = metodo.platform_account[0].value
        self.assertEqual(valor, "3009999999")

    def test_metodo_por_id(self):
        self.assertEqual(paises.metodo_por_id("nequi_co").country, "CO")
        self.assertIsNone(paises.metodo_por_id("no_existe"))

    def test_mapa_de_ip(self):
        for code in ("VE", "CO", "CL", "US"):
            self.assertEqual(paises.IP_COUNTRY_MAP[code], code)


if __name__ == "__main__":
    unittest.main()
