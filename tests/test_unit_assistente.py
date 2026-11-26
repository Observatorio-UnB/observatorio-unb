"""Testes leves do assistente de chat: lógica de envio/erro e renderização via AppTest (sem Ollama nem banco)."""

import sys
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

from src.dashboard import assistente


class ResponderTest(unittest.TestCase):
    def test_devolve_resposta_do_agente(self):
        r = {"resposta": "42", "consultas": ["SELECT 1"], "avisos": ["a"]}
        with mock.patch("src.chat.agente.conversar", return_value=r):
            self.assertEqual(assistente.responder([], "?"), ("42", ["SELECT 1"], ["a"]))

    def test_falha_vira_mensagem_amigavel(self):
        with mock.patch("src.chat.agente.conversar", side_effect=ConnectionError("ollama fora")):
            resposta, consultas, avisos = assistente.responder([], "?")
        self.assertEqual(resposta, assistente.MSG_INDISPONIVEL)
        self.assertNotIn("ollama fora", resposta)
        self.assertEqual((consultas, avisos), ([], []))


class SemLinksTest(unittest.TestCase):
    def test_remove_imagem_e_link_mantendo_texto(self):
        self.assertEqual(assistente.sem_links("![x](https://a.invalid/p?d=1) veja [aqui](http://b.invalid)"), "x veja aqui")

    def test_remove_imagem_por_referencia(self):
        self.assertEqual(assistente.sem_links("![x][r]\n\n[r]: https://a.invalid/?d=1").strip(), "x")

    def test_definicao_com_entidade_html_e_imagem_curta(self):
        for md in ("![x][r]\n\n[r]: h&#116;tp://a.invalid/?d=1", "![x][r]\n[r]: ftp://a.invalid/?d=1",
                   "![x]\n\n[x]: https://a.invalid/?d=1", "![x][]\n\n[x]: //a.invalid/?d=1", "![x][r]\n[r]: h\\ttp://a.invalid"):
            r = assistente.sem_links(md)
            self.assertNotIn("invalid", r)
            self.assertNotIn("![", r)

    def test_texto_com_dois_pontos_nao_e_definicao(self):
        self.assertEqual(assistente.sem_links("[Nota]: IRC alto"), "[Nota]: IRC alto")

    def test_texto_comum_intacto(self):
        self.assertEqual(assistente.sem_links("IRC 31.9 [1]"), "IRC 31.9 [1]")


class PerguntaPendenteTest(unittest.TestCase):
    def test_pergunta_interrompida_e_retomada(self):
        script = ("import streamlit as st\nfrom src.dashboard import assistente\n"
                  "assistente.conversa()")
        with mock.patch("src.chat.agente.conversar",
                        return_value={"resposta": "ok", "consultas": [], "avisos": []}) as c:
            at = AppTest.from_string(script)
            at.session_state["pergunta_em_curso"] = "pergunta perdida"
            at.run()
        self.assertFalse(at.exception)
        self.assertEqual(c.call_args[0][1], "pergunta perdida")
        self.assertIsNone(at.session_state["pergunta_em_curso"])
        self.assertEqual(len(at.session_state["exibicao"]), 2)


class TimeoutTest(unittest.TestCase):
    def test_timeout_do_ollama_vira_mensagem_de_preparo(self):
        import requests

        with mock.patch("src.chat.agente.conversar", side_effect=requests.exceptions.ReadTimeout()):
            resposta, consultas, avisos = assistente.responder([], "?")
        self.assertEqual(resposta, assistente.MSG_AQUECENDO)


class SqlEscondidoTest(unittest.TestCase):
    SCRIPT = ("from src.dashboard import assistente\n"
              "assistente.desenhar_mensagem('assistant', 'ok', ['SELECT 1'])")

    def test_sql_so_no_modo_de_depuracao(self):
        self.assertEqual(len(AppTest.from_string(self.SCRIPT).run().expander), 0)
        at = AppTest.from_string(self.SCRIPT)
        at.query_params["sql"] = "1"
        self.assertEqual(len(at.run().expander), 1)


class BolhaTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch("src.chat.agente.aquecer")  # sem chamar o Ollama de verdade
        self.aquecer = p.start()
        self.addCleanup(p.stop)
        assistente._aquecer_modelo.clear()

    SCRIPT = "from src.dashboard.assistente import renderizar_assistente\nrenderizar_assistente()"

    def test_renderiza_exemplos_e_botao_de_chat(self):
        at = AppTest.from_string(self.SCRIPT).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.button), len(assistente.EXEMPLOS))

    def test_some_no_stlite(self):
        with mock.patch.object(sys, "platform", "emscripten"):
            at = AppTest.from_string(self.SCRIPT).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.button), 0)


if __name__ == "__main__":
    unittest.main()
