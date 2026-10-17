import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from genresearch_servidor import GenResearch, embedding_simulado, fragmentar


class ParteBTest(unittest.TestCase):
    def test_fragmentos_e_vetores_deterministicos(self):
        texto = "A memoria virtual usa paginas. " * 30
        chunks = fragmentar(texto, 120)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))
        self.assertEqual(embedding_simulado("paginas RAM"), embedding_simulado("paginas RAM"))

    def test_armazenamento_fila_recuperacao_e_cache(self):
        with tempfile.TemporaryDirectory() as d:
            servidor = GenResearch(str(Path(d) / 'indice.sqlite3'),
                                   str(Path(d) / 'eventos.jsonl'),
                                   trabalhadores=2, capacidade_fila=4, capacidade_cache=2)
            try:
                info = servidor.ingerir('memoria.txt', 'A memoria virtual usa paginas e RAM. ' * 20, 120)
                self.assertGreater(info['trechos'], 1)
                s1 = servidor.consultar('Como a memoria virtual usa paginas?')
                s2 = servidor.consultar('Como a memoria virtual usa paginas?')
                self.assertEqual(s1['cache'], 'miss')
                self.assertEqual(s2['cache'], 'hit')
                self.assertGreater(len(s1['trechos']), 0)
                status = servidor.status()
                self.assertEqual(status['armazenamento']['documentos'], 1)
                self.assertEqual(status['fila_e_processamento']['requisições_concluídas'], 2)
                self.assertEqual(status['cache']['acertos'], 1)
                # Atualizar um documento invalida o cache.
                servidor.ingerir('memoria.txt', 'RAM paginação swap RAM' * 10, 100)
                s3 = servidor.consultar('Como a memoria virtual usa paginas?')
                self.assertEqual(s3['cache'], 'miss')
            finally:
                servidor.fechar()
            log = (Path(d) / 'eventos.jsonl').read_text(encoding='utf-8')
            self.assertIn('"evento": "ingestao"', log)
            self.assertIn('"evento": "recuperacao"', log)
            self.assertIn('"evento": "encerramento"', log)


if __name__ == '__main__':
    unittest.main()
