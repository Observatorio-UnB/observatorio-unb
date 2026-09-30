"""
API pública do Supabase usada pelo painel do GitHub Pages.

- cliente HTTP: contra um servidor local de mentira (sem rede);
- observatorio_gold(): mesmo conteúdo que src/db/exportar_gold.py (precisa do banco com a gold);
- Supabase de verdade: só roda com SUPABASE_URL e SUPABASE_ANON_KEY no ambiente.
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import supabase_rest  # noqa: E402
from src.db.conexao import conectar  # noqa: E402


class _Falso(BaseHTTPRequestHandler):
    pedidos = []

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers["Content-Length"])).decode()
        self.pedidos.append((self.path, {k.lower(): v for k, v in self.headers.items()}, json.loads(corpo)))
        if self.path.endswith("/rpc/quebra"):
            self.send_response(400)
            resposta = b'{"message":"tipo invalido"}'
        else:
            self.send_response(200)
            resposta = b'[{"ok": true}]'
        self.end_headers()
        self.wfile.write(resposta)

    def log_message(self, *args):
        pass


class TestClienteHttp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.servidor = HTTPServer(("127.0.0.1", 0), _Falso)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.servidor.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _config(self, chave):
        return mock.patch.dict(os.environ, {"SUPABASE_URL": self.url + "/", "SUPABASE_ANON_KEY": chave})

    def test_rpc_e_funcao_postam_no_caminho_certo(self):
        _Falso.pedidos.clear()
        with self._config("eyJlegada"):
            self.assertEqual(supabase_rest.rpc("observatorio_gold"), [{"ok": True}])
            self.assertEqual(supabase_rest.funcao("buscar", {"consulta": "x"}), [{"ok": True}])
        (caminho_rpc, cab_rpc, _), (caminho_fn, _, corpo_fn) = _Falso.pedidos
        self.assertEqual(caminho_rpc, "/rest/v1/rpc/observatorio_gold")
        self.assertEqual(caminho_fn, "/functions/v1/buscar")
        self.assertEqual(corpo_fn, {"consulta": "x"})
        self.assertEqual(cab_rpc["apikey"], "eyJlegada")
        self.assertEqual(cab_rpc["authorization"], "Bearer eyJlegada")

    def test_chave_publishable_nao_vai_em_authorization(self):
        _Falso.pedidos.clear()
        with self._config("sb_publishable_abc"):
            supabase_rest.rpc("observatorio_gold")
        cabecalhos = _Falso.pedidos[0][1]
        self.assertEqual(cabecalhos["apikey"], "sb_publishable_abc")
        self.assertNotIn("authorization", cabecalhos)

    def test_erro_http_vira_excecao_com_a_mensagem(self):
        with self._config("eyJlegada"), self.assertRaisesRegex(supabase_rest.ErroSupabase, "HTTP 400.*tipo invalido"):
            supabase_rest.rpc("quebra")

    def test_sem_configuracao(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_ANON_KEY": ""}), \
                mock.patch.object(supabase_rest, "CONFIG_NAVEGADOR", BASE_DIR / "nao_existe.json"):
            self.assertFalse(supabase_rest.configurado())
            with self.assertRaises(supabase_rest.ErroSupabase):
                supabase_rest.rpc("observatorio_gold")


class TestSnapshotDoBanco(unittest.TestCase):

    def test_observatorio_gold_devolve_o_mesmo_que_o_export_estatico(self):
        from src.db.exportar_gold import montar_snapshot

        try:
            with conectar(autocommit=True, connect_timeout=3) as conn:
                da_funcao = conn.execute("SELECT public.observatorio_gold()").fetchone()[0]
        except (psycopg.OperationalError, psycopg.errors.UndefinedFunction) as erro:
            raise unittest.SkipTest(f"Banco indisponível ou sem a migração 0018 ({erro})")
        do_export = montar_snapshot()
        if not do_export["tabelas"]["retencao_cursos_unb"]:
            raise unittest.SkipTest("Gold vazia. Rode: bash scripts/rodar_pipeline.sh")
        self.assertEqual(da_funcao["tabelas"], do_export["tabelas"])
        self.assertEqual(da_funcao["relatorios"], do_export["relatorios"])


@unittest.skipUnless(
    os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"),
    "Defina SUPABASE_URL e SUPABASE_ANON_KEY para testar o Supabase de verdade.",
)
class TestSupabaseDeVerdade(unittest.TestCase):

    def test_gold_publica(self):
        dados = supabase_rest.rpc("observatorio_gold")
        self.assertGreater(len(dados["tabelas"]["retencao_cursos_unb"]), 50)

    def test_busca_encontra_o_curso_pelo_nome(self):
        # Também confere que a Edge Function e busca.documentos usam o mesmo modelo: vetores de
        # modelos diferentes não deixariam MEDICINA entre os três primeiros.
        resultados = supabase_rest.funcao("buscar", {"consulta": "curso de medicina", "tipo": "curso", "k": 3})
        self.assertEqual(len(resultados), 3)
        self.assertIn("MEDICINA", [r["titulo"] for r in resultados])
        self.assertNotIn("embedding", resultados[0])

    def test_busca_rejeita_tipo_invalido(self):
        with self.assertRaisesRegex(supabase_rest.ErroSupabase, "HTTP 400"):
            supabase_rest.funcao("buscar", {"consulta": "medicina", "tipo": "senha"})


if __name__ == "__main__":
    unittest.main()
