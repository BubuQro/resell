import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.precios import (CONFIG_DEFAULT, calcular_precio_venta, extract_price,
                         is_captcha, parse_precio)


def dentro_de_rango(amazon, venta):
    return amazon * 0.70 - 1 <= venta <= amazon * 0.80 + 1e-9


class TestParsePrecio(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(parse_precio("$1,299.00"), 1299.0)
        self.assertEqual(parse_precio("$ 349"), 349.0)
        self.assertEqual(parse_precio(450), 450.0)

    def test_invalidos(self):
        for v in (None, "", "N/D", 0, "$0.00"):
            self.assertIsNone(parse_precio(v))


class TestPrecioVenta(unittest.TestCase):
    def test_tramos_sin_redondeo(self):
        cfg = dict(CONFIG_DEFAULT, terminar_en_9=False)
        self.assertEqual(calcular_precio_venta("$299.99", cfg), 239)   # 20 % (240 sería 19.997 %)
        self.assertEqual(calcular_precio_venta("$300.00", cfg), 225)   # 25 %
        self.assertEqual(calcular_precio_venta("$999.99", cfg), 750)   # 25 %
        self.assertEqual(calcular_precio_venta("$1,000.00", cfg), 700)  # 30 %

    def test_termina_en_9_y_respeta_rango(self):
        for amazon in (99, 149.5, 299.99, 300, 349, 512.4, 999, 1000, 1299, 4599.0, 18999):
            venta = calcular_precio_venta(amazon)
            self.assertTrue(dentro_de_rango(amazon, venta), (amazon, venta))
            self.assertEqual(venta % 10, 9, (amazon, venta))

    def test_sin_9_posible_respeta_rango(self):
        # Entre $25 y $28 no hay ningún precio terminado en 9
        self.assertEqual(calcular_precio_venta(35), 28)

    def test_precio_pequeno_no_fuerza_9(self):
        venta = calcular_precio_venta(15)
        self.assertEqual(venta, 12)

    def test_invalido(self):
        self.assertIsNone(calcular_precio_venta(""))
        self.assertIsNone(calcular_precio_venta(None))


class TestExtractPrice(unittest.TestCase):
    def test_prioriza_precio_a_pagar(self):
        html = ('<span class="a-price a-text-price"><span class="a-offscreen">$999.00</span></span>'
                '<div id="corePriceDisplay_desktop_feature_div"><span class="a-price">'
                '<span class="a-offscreen">$649.00</span></span></div>')
        self.assertEqual(extract_price(html), "$649.00")

    def test_entero_y_fraccion(self):
        html = '<span class="a-price"><span class="a-price-whole">1,234<span>.</span></span><span class="a-price-fraction">50</span></span>'
        self.assertEqual(extract_price(html), "$1234.50")

    def test_sin_precio(self):
        self.assertIsNone(extract_price("<html><body>No disponible</body></html>"))

    def test_captcha(self):
        self.assertTrue(is_captcha('<form action="/errors/validateCaptcha">'))
        self.assertFalse(is_captcha("<html>ok</html>"))


if __name__ == "__main__":
    unittest.main()
