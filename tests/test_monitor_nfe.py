"""Monitor de NF-e: assinatura do webhook (vetor fixo) e montagem das requisições (HTTP simulado)."""
from __future__ import annotations

import io
import json
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from fiscalapi_br import BadRequestError, FiscalAPI, verificar_assinatura
from fiscalapi_br.webhook import assinar

SEGREDO = "whsec_dGVzdGUtZG8tc2RrLWZpc2NhbGFwaQ"
TS = 1795294800
CORPO = b'{"id":"evt_0123456789abcdef0123456789abcdef","tipo":"teste","ocorrido_em":"2026-11-21T17:00:00-03:00"}'
V1 = "8b03e794ca99a1c2c684cf54191aae0af0f7d4e696ef598f9258365861fa8933"
V1_ANTERIOR = "31ed23b2a446bf7329ed246b1bd0e1a717f11b19244290f3b4c9acb0f3396846"
CHAVE = "35261111222333000181550010000001231123456787"


class AssinaturaTest(unittest.TestCase):
    def verificar(self, **kw):
        args = {
            "corpo_bruto": CORPO,
            "cabecalho_assinatura": f"v1={V1}",
            "cabecalho_timestamp": str(TS),
            "segredo": SEGREDO,
            "agora": TS + 10,
        }
        args.update(kw)
        return verificar_assinatura(**args)

    def test_vetor_fixo(self):
        self.assertEqual(assinar(SEGREDO, TS, CORPO), V1)
        self.assertEqual(assinar("whsec_anterior", TS, CORPO), V1_ANTERIOR)

    def test_aceita(self):
        self.assertTrue(self.verificar())
        self.assertTrue(self.verificar(corpo_bruto=CORPO.decode()))
        self.assertTrue(self.verificar(cabecalho_assinatura=f"v1={V1_ANTERIOR}, v1={V1}"))
        self.assertTrue(self.verificar(cabecalho_timestamp=TS))

    def test_recusa(self):
        self.assertFalse(self.verificar(corpo_bruto=CORPO + b" "))
        self.assertFalse(self.verificar(segredo="whsec_outro"))
        self.assertFalse(self.verificar(cabecalho_assinatura=V1))
        self.assertFalse(self.verificar(cabecalho_assinatura=f"v0={V1}"))
        self.assertFalse(self.verificar(cabecalho_assinatura="v1=çã"))
        self.assertFalse(self.verificar(cabecalho_assinatura=None))
        self.assertFalse(self.verificar(cabecalho_timestamp="abc"))
        self.assertFalse(self.verificar(cabecalho_timestamp=str(TS + 1)))

    def test_tolerancia(self):
        self.assertFalse(self.verificar(agora=TS + 301))
        self.assertFalse(self.verificar(agora=TS - 301))
        self.assertTrue(self.verificar(agora=TS + 301, tolerancia=600))


class _Resposta:
    def __init__(self, corpo: bytes):
        self._corpo = corpo

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RequisicoesTest(unittest.TestCase):
    def setUp(self):
        self.api = FiscalAPI("fapi_teste", base_url="https://api.exemplo", max_retries=0)
        self.chamadas = []
        self.respostas = []

        def urlopen(req, timeout=None):
            corpo = json.loads(req.data.decode()) if req.data else None
            self.chamadas.append((req.get_method(), req.full_url, corpo, dict(req.header_items())))
            status, dados = self.respostas.pop(0) if self.respostas else (200, {})
            raw = b"" if dados is None else json.dumps(dados).encode()
            if status >= 400:
                raise urllib.error.HTTPError(req.full_url, status, "erro", Message(), io.BytesIO(raw))
            return _Resposta(raw)

        patcher = mock.patch("urllib.request.urlopen", urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cadastrar(self):
        self.respostas.append((200, {"resultados": [], "aceitas": 1, "valor_cobrado": "0,03"}))
        r = self.api.cadastrar_chaves_monitor_nfe(
            [f"NFe {CHAVE[:4]}.{CHAVE[4:]}", {"chave": CHAVE, "status_conhecido": "cancelada"}], prazo_dias=30
        )
        self.assertEqual(r["valor_cobrado"], "0,03")
        metodo, url, corpo, headers = self.chamadas[0]
        self.assertEqual((metodo, url), ("POST", "https://api.exemplo/api/monitor-nfe/chaves"))
        self.assertEqual(headers["X-api-key"], "fapi_teste")
        self.assertEqual(
            corpo,
            {"chaves": [{"chave": CHAVE}, {"chave": CHAVE, "status_conhecido": "cancelada"}], "prazo_dias": 30},
        )

    def test_cadastrar_valida_antes(self):
        with self.assertRaises(ValueError):
            self.api.cadastrar_chaves_monitor_nfe([])
        with self.assertRaises(ValueError):
            self.api.cadastrar_chaves_monitor_nfe(CHAVE)
        with self.assertRaises(ValueError):
            self.api.cadastrar_chaves_monitor_nfe([CHAVE] * 1001)
        with self.assertRaises(ValueError):
            self.api.cadastrar_chaves_monitor_nfe([CHAVE], prazo_dias=181)
        self.assertEqual(self.chamadas, [])

    def test_remover_e_detalhe(self):
        self.respostas += [(200, {"removidas": 1, "nao_encontradas": []}), (204, None), (200, {"chave": CHAVE})]
        self.api.remover_chaves_monitor_nfe([CHAVE])
        self.assertIsNone(self.api.remover_chave_monitor_nfe(CHAVE))
        self.assertEqual(self.api.consultar_chave_monitor_nfe(CHAVE)["chave"], CHAVE)
        base = "https://api.exemplo/api/monitor-nfe/chaves"
        self.assertEqual(
            [(m, u) for m, u, _, _ in self.chamadas],
            [("POST", base + "/remover"), ("DELETE", f"{base}/{CHAVE}"), ("GET", f"{base}/{CHAVE}")],
        )
        self.assertEqual(self.chamadas[0][2], {"chaves": [CHAVE]})

    def test_listar_e_iterar(self):
        self.respostas += [
            (200, {"itens": [{"chave": "a"}, {"chave": "b"}], "proximo_cursor": "c1"}),
            (200, {"itens": [{"chave": "c"}], "proximo_cursor": None}),
        ]
        vistos = [i["chave"] for i in self.api.iterar_chaves_monitor_nfe(ativo=True, status="cancelada", limite=2)]
        self.assertEqual(vistos, ["a", "b", "c"])
        base = "https://api.exemplo/api/monitor-nfe/chaves"
        self.assertEqual(self.chamadas[0][1], base + "?status=cancelada&ativo=true&limite=2")
        self.assertEqual(self.chamadas[1][1], base + "?status=cancelada&ativo=true&cursor=c1&limite=2")

    def test_webhook(self):
        self.respostas += [
            (200, {"url": "https://exemplo.com/h", "segredo": "whsec_x"}),
            (200, {"url": "https://exemplo.com/h", "ativo": True}),
            (200, {"segredo": "whsec_y", "anterior_valido_ate": "2026-11-22T17:00:00-03:00"}),
            (202, {"id": "evt_1", "estado": "pendente"}),
            (204, None),
        ]
        self.assertEqual(self.api.cadastrar_webhook_monitor_nfe(" https://exemplo.com/h ")["segredo"], "whsec_x")
        self.assertTrue(self.api.consultar_webhook_monitor_nfe()["ativo"])
        self.assertEqual(self.api.rotacionar_segredo_webhook_monitor_nfe()["segredo"], "whsec_y")
        self.assertEqual(self.api.testar_webhook_monitor_nfe()["estado"], "pendente")
        self.api.remover_webhook_monitor_nfe()
        self.assertEqual(
            [(m, u.replace("https://api.exemplo", "")) for m, u, _, _ in self.chamadas],
            [
                ("PUT", "/api/monitor-nfe/webhook"),
                ("GET", "/api/monitor-nfe/webhook"),
                ("POST", "/api/monitor-nfe/webhook/rotacionar-segredo"),
                ("POST", "/api/monitor-nfe/webhook/teste"),
                ("DELETE", "/api/monitor-nfe/webhook"),
            ],
        )
        self.assertEqual(self.chamadas[0][2], {"url": "https://exemplo.com/h"})

    def test_404_vira_bad_request(self):
        self.respostas.append((404, {"title": "WEBHOOK_NAO_CADASTRADO", "detail": "Nenhum webhook cadastrado."}))
        with self.assertRaises(BadRequestError) as ctx:
            self.api.consultar_webhook_monitor_nfe()
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.code, "WEBHOOK_NAO_CADASTRADO")


if __name__ == "__main__":
    unittest.main()
