"""Testes funcionais do ensaio isolado de sincronização da Parte D."""
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.experimentos_d import executar_cenario  # noqa: E402


class TestParteD(unittest.TestCase):
    def test_corrida_controlada_quatro_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = executar_cenario('D1', 1, 4, 5, Path(tmp) / 'sem_lock')
            self.assertTrue(r['sucesso'])
            self.assertEqual(r['geracoes_realizadas'], 4)
            self.assertEqual(r['geracoes_duplicadas'], 3)
            self.assertEqual(r['cache_misses'], 4)
            self.assertEqual(r['cache_entradas'], 1)

    def test_correcao_mutex_quatro_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = executar_cenario('D2', 1, 4, 5, Path(tmp) / 'com_lock')
            self.assertTrue(r['sucesso'])
            self.assertEqual(r['geracoes_realizadas'], 1)
            self.assertEqual(r['geracoes_duplicadas'], 0)
            self.assertEqual(r['cache_hits'], 3)
            self.assertEqual(r['cache_entradas'], 1)

    def test_com_duas_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = executar_cenario('D1', 1, 2, 5, Path(tmp) / 'a')
            b = executar_cenario('D2', 1, 2, 5, Path(tmp) / 'b')
            self.assertEqual(a['geracoes_duplicadas'], 1)
            self.assertEqual(b['geracoes_duplicadas'], 0)


if __name__ == '__main__':
    unittest.main()
