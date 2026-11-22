"""Emissão de NFS-e: montagem das requisições (HTTP simulado) e assinatura com o vetor da documentação."""
from __future__ import annotations

import base64
import io
import json
import unittest
import urllib.error
from decimal import Decimal
from email.message import Message
from unittest import mock

from fiscalapi_br import BadRequestError, FiscalAPI, RateLimitError, ServerError, verificar_assinatura

# Empresa fictícia da documentação (CNPJ com DV válido, não é de cliente).
EMPRESA_ID = "8f1c2a4e-5b6d-4e7f-9a0b-1c2d3e4f5a6b"
NOTA_ID = "3b8e2f4a-6c1d-4e9f-8a7b-2c3d4e5f6a7b"
BASE = "https://api.exemplo"

NOTA = {
    "empresa_id": EMPRESA_ID,
    "ambiente": "homologacao",
    "referencia": "teste-0001",
    "preset": "simples_servico",
    "competencia": "2026-11-22",
    "tomador": {"tipo": "cnpj", "documento": "12.345.678/0001-95", "nome": "Cliente Exemplo Comercio Ltda"},
    "servico": {"codigo_tributacao_nacional": "01.07.01", "descricao": "Suporte técnico em informática"},
    "valores": {"valor_servico": "1500.00", "percentual_tributos_aproximado": "6.00"},
}


class _Resposta:
    def __init__(self, corpo: bytes):
        self._corpo = corpo

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class EmissaoNfseTest(unittest.TestCase):
    def setUp(self):
        self.api = FiscalAPI("fapi_teste", base_url=BASE, max_retries=0)
        self.chamadas = []
        self.respostas = []

        def urlopen(req, timeout=None):
            headers = dict(req.header_items())
            corpo = req.data
            if corpo and headers.get("Content-type") == "application/json":
                corpo = json.loads(corpo.decode())
            self.chamadas.append((req.get_method(), req.full_url, corpo, headers))
            status, dados = self.respostas.pop(0) if self.respostas else (200, {})
            if isinstance(dados, bytes):
                raw = dados
            else:
                raw = b"" if dados is None else json.dumps(dados).encode()
            if status >= 400:
                hdrs = Message()
                hdrs["Retry-After"] = "0"
                raise urllib.error.HTTPError(req.full_url, status, "erro", hdrs, io.BytesIO(raw))
            return _Resposta(raw)

        patcher = mock.patch("urllib.request.urlopen", urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)

    def rotas(self):
        return [(m, u.replace(BASE, "")) for m, u, _, _ in self.chamadas]

    def test_empresas(self):
        self.respostas += [
            (201, {"id": EMPRESA_ID, "verificada": True}),
            (200, [{"id": EMPRESA_ID}]),
            (200, {"id": EMPRESA_ID}),
            (200, {"id": EMPRESA_ID, "ativa": False}),
        ]
        empresa = {
            "cnpj": "11.222.333/0001-81",
            "razao_social": "Exemplo Servicos de Tecnologia Ltda",
            "im": "123456",
            "cod_mun_ibge": "4106902",
            "regime": {"op_simp_nac": 3, "reg_ap_trib_sn": 1},
            "serie": "00001",
        }
        self.assertTrue(self.api.criar_empresa_nfse(empresa)["verificada"])
        lista = self.api.listar_empresas_nfse()
        self.assertIsInstance(lista, list)
        self.assertEqual(lista[0]["id"], EMPRESA_ID)
        self.api.obter_empresa_nfse(EMPRESA_ID)
        self.assertFalse(self.api.atualizar_empresa_nfse(EMPRESA_ID, {"ativa": False})["ativa"])
        self.assertEqual(
            self.rotas(),
            [
                ("POST", "/api/nfse/empresas"),
                ("GET", "/api/nfse/empresas"),
                ("GET", f"/api/nfse/empresas/{EMPRESA_ID}"),
                ("PATCH", f"/api/nfse/empresas/{EMPRESA_ID}"),
            ],
        )
        self.assertEqual(self.chamadas[0][2], empresa)
        self.assertEqual(self.chamadas[3][2], {"ativa": False})
        with self.assertRaises(ValueError):
            self.api.atualizar_empresa_nfse(EMPRESA_ID, {})
        with self.assertRaises(ValueError):
            self.api.obter_empresa_nfse(" ")

    def test_certificado_multipart_e_exclusao(self):
        self.respostas += [(200, {"cnpj_raiz": "11222333"}), (200, {}), (204, None), (204, None)]
        pfx = b"\x30\x82\x01\x02"
        self.assertEqual(self.api.enviar_certificado_nfse(pfx, senha="s3nha")["cnpj_raiz"], "11222333")
        metodo, url, corpo, headers = self.chamadas[0]
        self.assertEqual((metodo, url), ("PUT", f"{BASE}/api/nfse/certificados"))
        tipo = headers["Content-type"]
        self.assertTrue(tipo.startswith("multipart/form-data; boundary="))
        fronteira = tipo.split("boundary=", 1)[1].encode()
        self.assertIn(b'name="senha"\r\n\r\ns3nha\r\n', corpo)
        self.assertIn(b'name="certificado"; filename="certificado.pfx"\r\n', corpo)
        self.assertIn(b"Content-Type: application/x-pkcs12\r\n\r\n" + pfx + b"\r\n", corpo)
        self.assertTrue(corpo.endswith(b"--" + fronteira + b"--\r\n"))

        # base64 também é aceito, com nome de arquivo
        self.api.enviar_certificado_nfse(base64.b64encode(pfx).decode(), nome_arquivo="empresa.pfx")
        self.assertIn(b'filename="empresa.pfx"', self.chamadas[1][2])
        self.assertIn(pfx, self.chamadas[1][2])

        self.api.excluir_certificado_nfse("11.222.333")
        self.api.excluir_certificado_nfse("11.222.333/0001-81")
        self.assertEqual(
            self.rotas()[2:],
            [("DELETE", "/api/nfse/certificados/11222333"), ("DELETE", "/api/nfse/certificados/11222333")],
        )
        with self.assertRaises(ValueError):
            self.api.excluir_certificado_nfse("123")

    def test_emitir(self):
        self.respostas += [(202, {"id": NOTA_ID, "status": "pendente"}), (202, {"id": NOTA_ID})]
        self.assertEqual(self.api.emitir_nfse(NOTA)["status"], "pendente")
        self.assertEqual(self.chamadas[0][2], NOTA)
        self.assertNotIn("Idempotency-key", self.chamadas[0][3])

        prod = {**NOTA, "ambiente": "producao", "valores": {"valor_servico": Decimal("1500.00")}}
        del prod["referencia"]
        self.api.emitir_nfse(prod, idempotency_key="pedido-1001")
        self.assertEqual(self.chamadas[1][3]["Idempotency-key"], "pedido-1001")
        self.assertEqual(self.chamadas[1][2]["valores"], {"valor_servico": "1500.00"})
        self.assertEqual(self.rotas(), [("POST", "/api/nfse/notas"), ("POST", "/api/nfse/notas")])

        with self.assertRaisesRegex(ValueError, "referencia"):
            self.api.emitir_nfse(prod)
        with self.assertRaisesRegex(ValueError, "diferentes"):
            self.api.emitir_nfse({**NOTA, "referencia": "a"}, idempotency_key="b")
        self.assertEqual(len(self.chamadas), 2)

    def test_emitir_com_referencia_repete_em_5xx(self):
        api = FiscalAPI("fapi_teste", base_url=BASE, max_retries=1)
        self.respostas += [(503, {"title": "FEATURE_UNDER_REVIEW"}), (202, {"id": NOTA_ID})]
        self.assertEqual(api.emitir_nfse(NOTA)["id"], NOTA_ID)
        self.assertEqual(len(self.chamadas), 2)

        sem_ref = dict(NOTA)
        del sem_ref["referencia"]
        self.respostas.append((503, {"title": "FEATURE_UNDER_REVIEW"}))
        with self.assertRaises(ServerError):
            api.emitir_nfse(sem_ref)
        self.assertEqual(len(self.chamadas), 3)

    def test_limite_de_homologacao_nao_repete(self):
        api = FiscalAPI("fapi_teste", base_url=BASE, max_retries=3)
        self.respostas.append((429, {"title": "NFSE_HOMOLOG_LIMITE", "status": 429, "detail": "Limite do mês."}))
        with self.assertRaises(RateLimitError) as ctx:
            api.emitir_nfse(NOTA)
        self.assertEqual(ctx.exception.code, "NFSE_HOMOLOG_LIMITE")
        self.assertEqual(len(self.chamadas), 1)

    def test_notas(self):
        self.respostas += [
            (200, {"id": NOTA_ID, "status": "autorizada"}),
            (200, {"itens": [{"id": "a"}, {"id": "b"}], "proximo": "c1"}),
            (200, {"itens": [{"id": "c"}], "proximo": None}),
            (202, {"id": NOTA_ID, "status": "cancelando"}),
            (202, {"id": "nova", "substitui_id": NOTA_ID}),
        ]
        self.assertEqual(self.api.obter_nfse(NOTA_ID)["status"], "autorizada")
        vistos = [
            n["id"]
            for n in self.api.iterar_nfse(
                ambiente="producao", status="autorizada", atualizada_desde="2026-11-22T00:00:00-03:00", limite=2
            )
        ]
        self.assertEqual(vistos, ["a", "b", "c"])
        cancel = self.api.cancelar_nfse(
            NOTA_ID, motivo=1, justificativa=" Valor do serviço informado errado na nota. "
        )
        self.assertEqual(cancel["status"], "cancelando")
        subst = {
            "referencia": "pedido-1001-v2",
            "motivo": "99",
            "justificativa": "Descrição do serviço corrigida a pedido do cliente.",
            "competencia": "2026-11-20",
            "tomador": NOTA["tomador"],
            "servico": NOTA["servico"],
            "valores": {**NOTA["valores"], "iss": {"tributacao": 1}},
        }
        self.assertEqual(self.api.substituir_nfse(NOTA_ID, subst)["substitui_id"], NOTA_ID)
        desde = "2026-11-22T00%3A00%3A00-03%3A00"
        self.assertEqual(
            self.rotas(),
            [
                ("GET", f"/api/nfse/notas/{NOTA_ID}"),
                ("GET", f"/api/nfse/notas?status=autorizada&ambiente=producao&atualizada_desde={desde}&limite=2"),
                (
                    "GET",
                    f"/api/nfse/notas?status=autorizada&ambiente=producao&atualizada_desde={desde}&cursor=c1&limite=2",
                ),
                ("POST", f"/api/nfse/notas/{NOTA_ID}/cancelamento"),
                ("POST", f"/api/nfse/notas/{NOTA_ID}/substituicao"),
            ],
        )
        self.assertEqual(
            self.chamadas[3][2], {"motivo": 1, "justificativa": "Valor do serviço informado errado na nota."}
        )
        self.assertEqual(self.chamadas[4][2], subst)
        with self.assertRaises(ValueError):
            self.api.cancelar_nfse(NOTA_ID, motivo=1, justificativa="curta")
        with self.assertRaises(ValueError):
            self.api.listar_nfse(limite=101)

    def test_xml_e_pdf(self):
        xml = '<?xml version="1.0" encoding="UTF-8"?><NFSe><infNFSe Id="NFS4106"/></NFSe>'
        pdf = b"%PDF-1.7\n"
        self.respostas += [
            (200, xml.encode()),
            (200, pdf),
            (409, {"title": "NFSE_NOTA_SEM_XML", "status": 409, "detail": "A nota ainda não foi autorizada."}),
        ]
        self.assertEqual(self.api.baixar_xml_nfse(NOTA_ID), xml)
        self.assertEqual(self.api.baixar_pdf_nfse(NOTA_ID), pdf)
        with self.assertRaises(BadRequestError) as ctx:
            self.api.baixar_pdf_nfse(NOTA_ID)
        self.assertEqual((ctx.exception.status_code, ctx.exception.code), (409, "NFSE_NOTA_SEM_XML"))
        self.assertEqual(
            self.rotas(),
            [
                ("GET", f"/api/nfse/notas/{NOTA_ID}/xml"),
                ("GET", f"/api/nfse/notas/{NOTA_ID}/pdf"),
                ("GET", f"/api/nfse/notas/{NOTA_ID}/pdf"),
            ],
        )
        self.assertEqual(self.chamadas[1][3]["Accept"], "application/pdf")

    def test_webhook(self):
        url = "https://seu-sistema.com.br/webhooks/nfse"
        self.respostas += [
            (200, {"url": url, "ativo": True, "segredo": "whsec_x"}),
            (200, {"url": url, "ativo": True, "segredo_final": "Y2Fv"}),
            (202, {"reenfileiradas": 1}),
            (204, None),
        ]
        self.assertEqual(self.api.configurar_webhook_nfse(f" {url} ")["segredo"], "whsec_x")
        self.assertEqual(self.api.obter_webhook_nfse()["segredo_final"], "Y2Fv")
        self.assertEqual(self.api.reenviar_webhook_nfse(NOTA_ID)["reenfileiradas"], 1)
        self.assertIsNone(self.api.remover_webhook_nfse())
        self.assertEqual(
            self.rotas(),
            [
                ("PUT", "/api/nfse/webhook"),
                ("GET", "/api/nfse/webhook"),
                ("POST", f"/api/nfse/notas/{NOTA_ID}/webhook"),
                ("DELETE", "/api/nfse/webhook"),
            ],
        )
        self.assertEqual(self.chamadas[0][2], {"url": url})


class AssinaturaEmissaoTest(unittest.TestCase):
    def test_vetor_da_documentacao(self):
        corpo = (
            b'{"id":"3b8e2f4a-6c1d-4e9f-8a7b-2c3d4e5f6a7b","status":"autorizada",'
            b'"ambiente":"homologacao","evento":"autorizada"}'
        )
        args = dict(
            corpo_bruto=corpo,
            cabecalho_assinatura="v1=0c95c6c219de4c9a004efd0b8896f1e8e0d36bd373d86eb859f65506d5c0b9ed",
            cabecalho_timestamp="1795439400",
            segredo="whsec_RXhlbXBsbyBkZSBzZWdyZWRvLCBuYW8gdXNlIGVtIHByb2R1Y2Fv",
            agora=1795439400,
        )
        self.assertTrue(verificar_assinatura(**args))
        self.assertFalse(verificar_assinatura(**{**args, "corpo_bruto": corpo.replace(b"homologacao", b"producao")}))
        self.assertFalse(verificar_assinatura(**{**args, "agora": 1795439400 + 301}))


if __name__ == "__main__":
    unittest.main()
