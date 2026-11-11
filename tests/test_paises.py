"""Pruebas del catálogo multi-país: países, monedas y métodos de pago."""

from __future__ import annotations

import unittest

from nucleo import paises


class PaisesTest(unittest.TestCase):
    def test_hay_todos_los_paises_del_mundo(self):
        codigos = [p.code for p in paises.PAISES]
        self.assertGreaterEqual(len(codigos), 200)
        for esperado in ("VE", "CO", "CL", "US", "JP", "DE", "IN", "NG", "BR"):
            self.assertIn(esperado, codigos)
        # Sin repetidos.
        self.assertEqual(len(codigos), len(set(codigos)))

    def test_todos_los_paises_usan_el_dolar(self):
        for p in paises.PAISES:
            self.assertEqual(p.moneda, "USD", f"{p.code} no está en dólares")
            # El símbolo es el gesto de mano 🫰, no el dólar.
            self.assertEqual(p.simbolo, "🫰", f"{p.code} no usa el símbolo 🫰")
            # La bandera se calcula sola desde el código ISO.
            self.assertTrue(p.bandera, f"{p.code} sin bandera")

    def test_todos_los_paises_ofrecen_paypal_y_cripto(self):
        for p in paises.PAISES:
            ids = [m.id for m in paises.metodos_de_pais(p.code)]
            self.assertEqual(ids, ["paypal", "cripto"], f"{p.code} no ofrece PayPal y cripto")

    def test_pais_desconocido_no_revienta(self):
        self.assertIsNone(paises.pais("XX"))
        self.assertFalse(paises.es_pais_valido("XX"))
        # Un país raro cae al de por defecto, no rompe el formateo.
        self.assertEqual(paises.simbolo_de("XX"), "🫰")

    def test_formateo_siempre_en_dolares(self):
        # El dinero es el mismo en todo el mundo; el símbolo es 🫰.
        self.assertEqual(paises.formatear(123450, "VE"), "🫰 1.234,50")
        self.assertEqual(paises.formatear(123450, "CO"), "🫰 1.234,50")
        self.assertEqual(paises.formatear(123450, "CL"), "🫰 1.234,50")
        self.assertEqual(paises.formatear(123450, "US"), "🫰 1.234,50")
        self.assertEqual(paises.formatear(123450, "JP"), "🫰 1.234,50")

    def test_formateo_negativo(self):
        self.assertEqual(paises.formatear(-500, "VE"), "-🫰 5,00")

    def test_no_hay_conversion_entre_paises(self):
        from nucleo.money import a_texto

        # Sin importar el país activo, el importe es el mismo: no se convierte.
        for code in ("VE", "CO", "CL", "US"):
            with self.subTest(code=code):
                paises.usar_pais(code)
                self.assertEqual(a_texto(999900), "🫰 9.999,00")
        paises.usar_pais("VE")

    def test_la_moneda_base_no_convierte(self):
        self.assertEqual(paises.PAIS_BASE, "US")
        for code in ("VE", "CO", "CL", "US"):
            self.assertEqual(paises.tasa_de(code), 1)
            self.assertEqual(paises.a_base(12345, code), 12345)
            self.assertEqual(paises.de_base(12345, code), 12345)

    def test_una_tasa_puesta_en_el_entorno_se_ignora(self):
        # Aunque alguien ponga una tasa vieja en Render, ya no se usa: no hay
        # conversión. Esto evita que un resto de la configuración antigua mueva
        # el dinero.
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_TASA_US": "50"}):
            self.assertEqual(paises.tasa_de("US"), 1)
            self.assertEqual(paises.a_base(1_000, "US"), 1_000)

    def test_formatear_local_usa_dolares(self):
        self.assertEqual(paises.formatear_local(40_000, "US"), "🫰 400,00")
        self.assertEqual(paises.formatear_local(40_000, "VE"), "🫰 400,00")

    def test_un_pais_invalido_no_cambia_el_activo(self):
        paises.usar_pais("VE")
        elegido = paises.usar_pais("ZZ")
        self.assertEqual(elegido, "VE")
        self.assertEqual(paises.pais_actual(), "VE")

    def test_el_catalogo_trae_todo_lo_que_el_front_necesita(self):
        cat = paises.catalogo()
        self.assertGreaterEqual(len(cat["paises"]), 200)
        # Solo dos métodos, los mismos para todos: PayPal y cripto (USDT).
        self.assertEqual(len(cat["metodos_pago"]), 2)
        self.assertEqual([m["id"] for m in cat["metodos_pago"]], ["paypal", "cripto"])
        self.assertEqual(cat["pais_por_defecto"], "VE")
        paypal = next(m for m in cat["metodos_pago"] if m["id"] == "paypal")
        self.assertTrue(paypal["platformAccount"])
        self.assertTrue(paypal["fields"])

    def test_paypal_y_cripto_son_iguales_en_todos_los_paises(self):
        for code in ("VE", "CO", "CL", "US"):
            self.assertEqual([m.id for m in paises.metodos_de_pais(code)],
                             ["paypal", "cripto"])

    def test_la_cuenta_de_administracion_es_una_sola(self):
        cuentas = paises.cuentas_admin()
        # Una sola cuenta para todo el mundo: PayPal y la billetera USDT.
        self.assertEqual(len(cuentas), 1)
        c = cuentas[0]
        self.assertEqual([l.label for l in c.lineas], ["PayPal", "Billetera USDT"])

    def test_la_cuenta_de_administracion_sale_del_entorno(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {
            "BINGO_ADMIN_PAYPAL": "casa@correo.com",
            "BINGO_ADMIN_CRIPTO": "TXYZ1234567890",
        }):
            c = paises.cuenta_admin("VE")
            self.assertTrue(c.configurada)
            valores = [l.valor for l in c.lineas]
            self.assertIn("casa@correo.com", valores)
            self.assertIn("TXYZ1234567890", valores)

    def test_el_paypal_de_la_casa_sale_del_entorno(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_PAGO_PAYPAL": "otro@correo.com"}):
            metodo = paises.metodo_de_pais("VE")
            valores = {d.value for d in metodo.platform_account}
        self.assertIn("otro@correo.com", valores)

    def test_la_billetera_cripto_sale_del_entorno(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"BINGO_PAGO_CRIPTO_DIRECCION": "TABCDEF123456"}):
            metodo = paises.metodo_por_id("cripto")
            valores = {d.value for d in metodo.platform_account}
        self.assertIn("TABCDEF123456", valores)

    def test_metodo_por_id(self):
        self.assertEqual(paises.metodo_por_id("cripto").country, "*")
        self.assertIsNone(paises.metodo_por_id("no_existe"))

    def test_mapa_de_ip(self):
        for code in ("VE", "CO", "CL", "US", "JP", "DE", "IN"):
            self.assertEqual(paises.IP_COUNTRY_MAP[code], code)

    def test_la_bandera_sale_del_codigo(self):
        self.assertEqual(paises.bandera_de("VE"), "🇻🇪")
        self.assertEqual(paises.bandera_de("JP"), "🇯🇵")
        self.assertEqual(paises.bandera_de("US"), "🇺🇸")
        self.assertEqual(paises.bandera_de("ve"), "🇻🇪")
        self.assertEqual(paises.bandera_de("XX1"), "🏳️")


if __name__ == "__main__":
    unittest.main()
