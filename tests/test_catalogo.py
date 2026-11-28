import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import catalogo


class TestCatalogo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.prod = os.path.join(d, "productos.json")
        self.est = os.path.join(d, "estado_productos.json")
        with open(self.prod, "w") as f:
            json.dump([{"id": "B000000001", "titulo": "Viejo"}], f)
        with open(self.est, "w") as f:
            json.dump({"B000000001": {"precio": 100, "folio": "7", "vendido": False}}, f)
        self.patches = [
            mock.patch.object(catalogo, "PRODUCTOS_FILE", self.prod),
            mock.patch.object(catalogo, "ESTADO_FILE", self.est),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_agrega_solo_nuevos(self):
        nuevos = catalogo.agregar_productos([
            {"id": "B000000001", "titulo": "Duplicado"},
            {"id": "B000000002", "titulo": "Nuevo", "imagenes": ["http://x"]},
        ])
        self.assertEqual([p["id"] for p in nuevos], ["B000000002"])
        self.assertNotIn("imagenes", nuevos[0])
        self.assertEqual(catalogo.ids_catalogo(), {"B000000001", "B000000002"})
        estado = catalogo.cargar_estado()
        self.assertEqual(estado["B000000002"], catalogo.ESTADO_INICIAL)
        self.assertEqual(estado["B000000001"]["folio"], "7")
        self.assertTrue(os.path.exists(self.prod + ".bak"))

    def test_actualizar_estado_no_pisa_cambios_externos(self):
        # Simula que admin.html cambió el folio después de que el pipeline leyó
        with open(self.est, "w") as f:
            json.dump({"B000000001": {"precio": 100, "folio": "99", "vendido": True}}, f)
        catalogo.actualizar_estado({"B000000001": {"amazon_precio": "$150.00"}})
        e = catalogo.cargar_estado()["B000000001"]
        self.assertEqual(e["folio"], "99")
        self.assertTrue(e["vendido"])
        self.assertEqual(e["amazon_precio"], "$150.00")

    def test_excluidos_extension(self):
        path = os.path.join(self.tmp.name, "excluir.json")
        with open(path, "w") as f:
            json.dump([{"id": "b0abc12345"}, "B0XYZ00000", {"asin": "B0QQQ11111"}], f)
        self.assertEqual(catalogo.ids_excluidos_extension(path),
                         {"B0ABC12345", "B0XYZ00000", "B0QQQ11111"})

    def test_bloqueo_impide_doble_ejecucion(self):
        lock = os.path.join(self.tmp.name, ".lock")
        with mock.patch.object(catalogo, "LOCK_FILE", lock):
            with catalogo.bloqueo_pipeline():
                with self.assertRaises(RuntimeError):
                    with catalogo.bloqueo_pipeline():
                        pass
            with catalogo.bloqueo_pipeline():  # liberado
                pass


if __name__ == "__main__":
    unittest.main()
