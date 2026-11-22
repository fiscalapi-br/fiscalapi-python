"""Cliente HTTP da FiscalAPI — somente biblioteca padrão (zero dependências)."""
from __future__ import annotations

import base64
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union, cast

from ._errors import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    FiscalAPIError,
    InsufficientBalanceError,
    RateLimitError,
    ServerError,
)
from ._version import __version__
from .types import (
    AmbienteNfse,
    CadastroMonitorResponse,
    CertidaoFederalResponse,
    CertidoesTodasResponse,
    CertificadoNfse,
    ChaveMonitorada,
    ChaveMonitoradaDetalhe,
    ChaveParaMonitorar,
    CNDResponse,
    CNDTodosResponse,
    CnirResponse,
    CNPJResponse,
    ConsultaIEResponse,
    ConsultaIETodosResponse,
    CteXmlResponse,
    DifalSaidaResponse,
    EmpresaNfse,
    EmpresaNfseIn,
    EmpresaNfsePatch,
    ListaChavesMonitoradas,
    NfeXmlResponse,
    NfseResponse,
    NotaNfse,
    NotaNfseIn,
    PaginaNotasNfse,
    PerfilProdutorResponse,
    ReenvioWebhookNfse,
    RemoverMonitorResponse,
    SegredoWebhookRotacionado,
    SigefParcelaResponse,
    SigefResponse,
    SimplesNacionalResponse,
    StatusMonitorNfe,
    StatusNotaNfse,
    SubstituicaoNfseIn,
    TesteWebhookEnfileirado,
    WebhookMonitorAtual,
    WebhookMonitorCriado,
    WebhookNfse,
    WebhookNfseConfigurado,
)

DEFAULT_BASE_URL = "https://api.fiscalapi.com.br"
# Algumas consultas (NF-e, SIGEF) podem levar até 180 s no servidor.
DEFAULT_TIMEOUT = 200.0
DEFAULT_MAX_RETRIES = 3

_RETRYABLE_ANY_METHOD = {429}
_RETRYABLE_IDEMPOTENT = {500, 502, 503, 504}
_MAX_BACKOFF = 30.0
_MAX_RETRY_AFTER = 60.0

Certificado = Union[bytes, bytearray, str, "os.PathLike[str]"]

MONITOR_NFE_MAX_LOTE = 1000
_MONITOR = "/api/monitor-nfe"
_NFSE = "/api/nfse"


class FiscalAPI:
    """Cliente da FiscalAPI.

    Exemplo::

        from fiscalapi_br import FiscalAPI

        api = FiscalAPI("sua-chave")
        resp = api.consultar_ie(uf="MT", cpf="12345678909")

    Args:
        api_key: chave de API do painel. Se omitida, lê ``FISCALAPI_API_KEY``.
        base_url: URL base da API.
        timeout: tempo máximo, em segundos, de cada tentativa.
        max_retries: novas tentativas em 429 e (para GET) em 5xx/falha de rede.
        user_agent: sufixo opcional para o cabeçalho ``User-Agent``.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        user_agent: Optional[str] = None,
    ) -> None:
        key = api_key or os.environ.get("FISCALAPI_API_KEY")
        if not key:
            raise ValueError(
                "Informe a chave de API: FiscalAPI('sua-chave') ou a variável FISCALAPI_API_KEY."
            )
        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        ua = f"fiscalapi-br-python/{__version__}"
        self.user_agent = f"{ua} {user_agent}" if user_agent else ua

    # ------------------------------------------------------------------ IE

    def consultar_ie(
        self,
        uf: str,
        *,
        cpf: Optional[str] = None,
        cnpj: Optional[str] = None,
        ie: Optional[str] = None,
        secundarias: bool = False,
    ) -> ConsultaIEResponse:
        """Inscrição Estadual em uma UF (``GET /api/consultar``).

        Informe exatamente um entre ``cpf``, ``cnpj`` e ``ie``. Com
        ``secundarias=True`` a resposta traz as atividades secundárias
        (``cnaes_secundarios``) — a consulta fica mais lenta.
        """
        doc = _um_documento(cpf=cpf, cnpj=cnpj, ie=ie)
        params = {"uf": _uf(uf), **doc, "secundarias": secundarias or None}
        return cast(ConsultaIEResponse, self._get("/api/consultar", params))

    def consultar_ie_todos(
        self,
        *,
        cpf: Optional[str] = None,
        cnpj: Optional[str] = None,
        ie: Optional[str] = None,
        secundarias: bool = False,
    ) -> ConsultaIETodosResponse:
        """Inscrição Estadual em todos os estados (``GET /api/consultar-ie-todos``).

        Confira ``complete``: quando ``False``, algum estado falhou e um
        resultado vazio não significa "não encontrado".
        """
        doc = _um_documento(cpf=cpf, cnpj=cnpj, ie=ie)
        params = {**doc, "secundarias": secundarias or None}
        return cast(ConsultaIETodosResponse, self._get("/api/consultar-ie-todos", params))

    # ---------------------------------------------------------------- CNPJ

    def consultar_cnpj(self, cnpj: str, *, force_fresh: bool = False) -> CNPJResponse:
        """Dados cadastrais do CNPJ na Receita Federal (``GET /api/consultar-cnpj``).

        ``force_fresh=True`` consulta o dado atual, sem cache (mais lento e
        consome mais créditos).
        """
        if not cnpj:
            raise ValueError("Informe o CNPJ.")
        params = {"cnpj": cnpj, "force_fresh": force_fresh or None}
        return cast(CNPJResponse, self._get("/api/consultar-cnpj", params))

    def consultar_simples_nacional(self, cnpj: str) -> SimplesNacionalResponse:
        """Situação no Simples Nacional e SIMEI (``GET /api/consultar-simples-nacional``)."""
        if not cnpj or not cnpj.strip():
            raise ValueError("Informe o CNPJ.")
        return cast(
            SimplesNacionalResponse,
            self._get("/api/consultar-simples-nacional", {"cnpj": cnpj.strip()}),
        )

    # ----------------------------------------------------------- Certidões

    def consultar_cnd(
        self, uf: str, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> CNDResponse:
        """CND estadual (ICMS) em uma UF (``GET /api/consultar-cnd``)."""
        params = {"uf": _uf(uf), **_um_documento(cpf=cpf, cnpj=cnpj)}
        return cast(CNDResponse, self._get("/api/consultar-cnd", params))

    def consultar_cnd_todos(
        self, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> CNDTodosResponse:
        """CND estadual em todos os estados disponíveis (``GET /api/consultar-cnd-todos``)."""
        params = _um_documento(cpf=cpf, cnpj=cnpj)
        return cast(CNDTodosResponse, self._get("/api/consultar-cnd-todos", params))

    def consultar_cnd_federal(
        self,
        *,
        cpf: Optional[str] = None,
        cnpj: Optional[str] = None,
        data_nascimento: Optional[str] = None,
        emitir_nova: bool = False,
    ) -> CertidaoFederalResponse:
        """CND Federal — Receita Federal + PGFN (``GET /api/consultar-cnd-federal``).

        Devolve a certidão vigente quando ela vale por mais de 3 dias
        (``modo="consulta"``); senão, emite uma nova (``modo="emissao"``).
        ``emitir_nova=True`` força uma nova emissão.

        Para CPF, a Receita exige ``data_nascimento`` do titular
        (``DD/MM/AAAA`` ou ``AAAA-MM-DD``).
        """
        doc = _um_documento(cpf=cpf, cnpj=cnpj)
        nascimento = (data_nascimento or "").strip()
        if "cpf" in doc and not nascimento:
            raise ValueError("Informe data_nascimento: a CND Federal de CPF exige a data de nascimento.")
        params = {
            **doc,
            "data_nascimento": nascimento if "cpf" in doc else None,
            "emitir_nova": emitir_nova or None,
        }
        return cast(CertidaoFederalResponse, self._get("/api/consultar-cnd-federal", params))

    def consultar_cndt(
        self, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> CertidaoFederalResponse:
        """CNDT — débitos trabalhistas (``GET /api/consultar-cndt``)."""
        params = _um_documento(cpf=cpf, cnpj=cnpj)
        return cast(CertidaoFederalResponse, self._get("/api/consultar-cndt", params))

    def consultar_crf_fgts(
        self, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> CertidaoFederalResponse:
        """CRF — regularidade do FGTS (``GET /api/consultar-crf-fgts``)."""
        params = _um_documento(cpf=cpf, cnpj=cnpj)
        return cast(CertidaoFederalResponse, self._get("/api/consultar-crf-fgts", params))

    def consultar_certidoes_todas(
        self,
        *,
        cpf: Optional[str] = None,
        cnpj: Optional[str] = None,
        skip_estaduais: bool = False,
    ) -> CertidoesTodasResponse:
        """CNDs estaduais + CNDT + CND Federal + CRF/FGTS em uma chamada
        (``GET /api/certidoes-todas``)."""
        params = {**_um_documento(cpf=cpf, cnpj=cnpj), "skip_estaduais": skip_estaduais or None}
        return cast(CertidoesTodasResponse, self._get("/api/certidoes-todas", params))

    # ---------------------------------------------------------------- NF-e

    def consultar_nfe_xml(
        self,
        chave: str,
        *,
        certificado: Certificado,
        senha: str,
        manifestar: bool = True,
    ) -> NfeXmlResponse:
        """XML completo de uma NF-e pela chave de acesso (``POST /api/consultar-nfe-xml``).

        Args:
            chave: chave de acesso com 44 dígitos.
            certificado: certificado A1 (.pfx/.p12) do participante da nota —
                caminho do arquivo, ``bytes`` do arquivo ou o conteúdo já em
                base64. O certificado não é armazenado pela API.
            senha: senha do certificado.
            manifestar: quando só há o resumo da nota, registra a manifestação
                do destinatário para liberar o XML. ``False`` não registra
                nenhum evento.
        """
        if not chave:
            raise ValueError("Informe a chave de acesso.")
        body = {
            "chave": "".join(ch for ch in chave if ch.isdigit()),
            "certificado": _certificado_base64(certificado),
            "senha": senha,
            "manifestar": manifestar,
        }
        # POST não é repetido em 5xx: a manifestação pode já ter sido registrada.
        return cast(NfeXmlResponse, self._request("POST", "/api/consultar-nfe-xml", json_body=body))

    def consultar_cte_xml(
        self,
        chave: str,
        *,
        certificado: Certificado,
        senha: str,
    ) -> CteXmlResponse:
        """XML completo de um CT-e, CT-e OS ou GTV-e pela chave de acesso (``POST /api/consultar-cte-xml``).

        Args:
            chave: chave de acesso com 44 dígitos.
            certificado: certificado A1 (.pfx/.p12) do participante do documento —
                caminho do arquivo, ``bytes`` do arquivo ou o conteúdo já em
                base64. O certificado não é armazenado pela API.
            senha: senha do certificado.
        """
        if not chave:
            raise ValueError("Informe a chave de acesso.")
        body = {
            # Aceita CNPJ alfanumérico: só tira separadores e põe em maiúsculas.
            "chave": "".join(ch for ch in chave if ch.isascii() and ch.isalnum()).upper(),
            "certificado": _certificado_base64(certificado),
            "senha": senha,
        }
        # POST não é repetido em 5xx.
        return cast(CteXmlResponse, self._request("POST", "/api/consultar-cte-xml", json_body=body))

    def consultar_difal_saida(
        self,
        competencia: str,
        *,
        certificado: Certificado,
        senha: str,
        ufs: Optional[Sequence[str]] = None,
    ) -> DifalSaidaResponse:
        """DIFAL de saída (EC 87/2015) por UF de destino, num mês (``POST /api/consultar-difal-saida``). Beta.

        Lista as NF-e do emitente com DIFAL e FCP destacados, a situação da
        guia de cada nota e o valor em aberto. Cobra 1 consulta por UF com
        ``status`` "ok". Pode levar cerca de 70 s.

        Args:
            competencia: mês de emissão das notas, ``AAAA-MM`` (ex.: "2026-10").
            certificado: certificado A1 (.pfx/.p12) do EMITENTE das notas —
                caminho do arquivo, ``bytes`` do arquivo ou o conteúdo já em
                base64. O certificado não é armazenado pela API.
            senha: senha do certificado.
            ufs: siglas das UFs de destino. Omitido ou vazio = as 10 atendidas
                (AC, AP, DF, GO, MS, MT, RR, RS, SC, SE).
        """
        competencia = (competencia or "").strip()
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia):
            raise ValueError("Informe a competência no formato AAAA-MM (ex.: 2026-10).")
        if isinstance(ufs, str):
            raise ValueError('Informe as UFs em lista, ex.: ["RS", "SC"].')
        body: Dict[str, Any] = {
            "certificado": _certificado_base64(certificado),
            "senha": senha,
            "competencia": competencia,
        }
        if ufs:
            body["ufs"] = [_uf(u) for u in ufs]
        # POST não é repetido em 5xx.
        return cast(DifalSaidaResponse, self._request("POST", "/api/consultar-difal-saida", json_body=body))

    def consultar_nfse(self, chave: str, *, danfse: bool = False) -> NfseResponse:
        """NFS-e (padrão nacional) pela chave de acesso, sem certificado (``GET /api/consultar-nfse``).

        ``danfse=True`` inclui o PDF do DANFSe em base64. Uma consulta nova
        pode levar de 30 a 60 segundos.
        """
        digitos = "".join(c for c in (chave or "") if c.isdigit())
        if not digitos:
            raise ValueError("Informe a chave de acesso.")
        params = {"chave": digitos, "danfse": danfse or None}
        return cast(NfseResponse, self._get("/api/consultar-nfse", params))


    # ----------------------------------------------------- Monitor de NF-e

    def cadastrar_chaves_monitor_nfe(
        self,
        chaves: Sequence[Union[str, ChaveParaMonitorar]],
        *,
        prazo_dias: Optional[int] = None,
    ) -> CadastroMonitorResponse:
        """Coloca até 1.000 chaves de NF-e no monitor (``POST /api/monitor-nfe/chaves``).

        Cada chave aceita é cobrada uma vez e acompanhada por até ``prazo_dias``
        (1 a 180, padrão 180). Chave já monitorada não é cobrada de novo; chave
        inválida volta com ``motivo``, sem cobrança. Sem saldo para todas as
        aceitas, levanta ``InsufficientBalanceError`` (402) e nenhuma entra.

        Args:
            chaves: chaves (str) ou dicionários ``{"chave": ..., "status_conhecido": ...}``
                (padrão ``"autorizada"``: o primeiro aviso só sai se a situação mudar).
            prazo_dias: dias de monitoramento, de 1 a 180.
        """
        itens = []
        for item in _lote(chaves):
            if isinstance(item, str):
                itens.append({"chave": _chave_nfe(item)})
            else:
                novo: Dict[str, Any] = {"chave": _chave_nfe(item.get("chave", ""))}
                if item.get("status_conhecido"):
                    novo["status_conhecido"] = item["status_conhecido"]
                itens.append(novo)
        body: Dict[str, Any] = {"chaves": itens}
        if prazo_dias is not None:
            if isinstance(prazo_dias, bool) or not isinstance(prazo_dias, int) or not 1 <= prazo_dias <= 180:
                raise ValueError("prazo_dias deve ser um inteiro de 1 a 180.")
            body["prazo_dias"] = prazo_dias
        # POST não é repetido em 5xx.
        return cast(CadastroMonitorResponse, self._request("POST", f"{_MONITOR}/chaves", json_body=body))

    def remover_chaves_monitor_nfe(self, chaves: Sequence[str]) -> RemoverMonitorResponse:
        """Para de monitorar até 1.000 chaves (``POST /api/monitor-nfe/chaves/remover``).

        Sem estorno e sem aviso no webhook.
        """
        body = {"chaves": [_chave_nfe(c) for c in _lote(chaves)]}
        return cast(RemoverMonitorResponse, self._request("POST", f"{_MONITOR}/chaves/remover", json_body=body))

    def remover_chave_monitor_nfe(self, chave: str) -> None:
        """Para de monitorar uma chave (``DELETE /api/monitor-nfe/chaves/{chave}``).

        Chave fora do monitor: ``BadRequestError`` com ``status_code`` 404.
        """
        self._request("DELETE", f"{_MONITOR}/chaves/{_chave_nfe(chave)}")

    def listar_chaves_monitor_nfe(
        self,
        *,
        status: Optional[StatusMonitorNfe] = None,
        ativo: Optional[bool] = None,
        alterado_desde: Optional[Union[str, datetime]] = None,
        cursor: Optional[str] = None,
        limite: Optional[int] = None,
    ) -> ListaChavesMonitoradas:
        """Uma página das chaves monitoradas (``GET /api/monitor-nfe/chaves``).

        Args:
            status: só notas nesta situação.
            ativo: ``True`` só monitoramentos correndo; ``False`` só os encerrados.
            alterado_desde: só o que mudou a partir deste instante. O servidor
                volta 5 minutos: itens podem repetir (deduplique por ``chave`` +
                ``atualizada_em``). Sem fuso = horário de Brasília.
            cursor: ``proximo_cursor`` da página anterior.
            limite: itens por página, de 1 a 1.000 (padrão do servidor: 100).
        """
        params = _query_listagem(status, ativo, alterado_desde, cursor, limite)
        return cast(ListaChavesMonitoradas, self._get(f"{_MONITOR}/chaves", params))

    def iterar_chaves_monitor_nfe(
        self,
        *,
        status: Optional[StatusMonitorNfe] = None,
        ativo: Optional[bool] = None,
        alterado_desde: Optional[Union[str, datetime]] = None,
        limite: Optional[int] = None,
    ) -> Iterator[ChaveMonitorada]:
        """Percorre todas as páginas da listagem, seguindo ``proximo_cursor``.

        Exemplo::

            for item in api.iterar_chaves_monitor_nfe(ativo=True):
                print(item["chave"], item["status"])
        """
        cursor: Optional[str] = None
        while True:
            pagina = self.listar_chaves_monitor_nfe(
                status=status, ativo=ativo, alterado_desde=alterado_desde, cursor=cursor, limite=limite
            )
            for item in pagina.get("itens") or []:
                yield item
            cursor = pagina.get("proximo_cursor")
            if not cursor:
                return

    def consultar_chave_monitor_nfe(self, chave: str) -> ChaveMonitoradaDetalhe:
        """Situação, eventos, próxima verificação e entregas que falharam de uma chave
        (``GET /api/monitor-nfe/chaves/{chave}``)."""
        return cast(ChaveMonitoradaDetalhe, self._get(f"{_MONITOR}/chaves/{_chave_nfe(chave)}", {}))

    def cadastrar_webhook_monitor_nfe(self, url: str) -> WebhookMonitorCriado:
        """Cadastra ou troca a URL do webhook (``PUT /api/monitor-nfe/webhook``).

        Só ``https`` na porta 443, com nome público. O ``segredo`` volta só
        aqui: guarde-o. Cadastrar de novo gera outro segredo e reativa o webhook.
        """
        url = (url or "").strip()
        if not url:
            raise ValueError("Informe a URL do webhook.")
        return cast(WebhookMonitorCriado, self._request("PUT", f"{_MONITOR}/webhook", json_body={"url": url}))

    def consultar_webhook_monitor_nfe(self) -> WebhookMonitorAtual:
        """URL cadastrada e se os avisos estão saindo (``GET /api/monitor-nfe/webhook``)."""
        return cast(WebhookMonitorAtual, self._get(f"{_MONITOR}/webhook", {}))

    def remover_webhook_monitor_nfe(self) -> None:
        """Remove o webhook (``DELETE /api/monitor-nfe/webhook``). O monitoramento continua."""
        self._request("DELETE", f"{_MONITOR}/webhook")

    def rotacionar_segredo_webhook_monitor_nfe(self) -> SegredoWebhookRotacionado:
        """Gera um segredo novo (``POST /api/monitor-nfe/webhook/rotacionar-segredo``).

        Por 24 h os avisos levam as duas assinaturas (``v1=nova,v1=anterior``).
        """
        return cast(SegredoWebhookRotacionado, self._request("POST", f"{_MONITOR}/webhook/rotacionar-segredo"))

    def testar_webhook_monitor_nfe(self) -> TesteWebhookEnfileirado:
        """Enfileira um aviso ``tipo="teste"`` (``POST /api/monitor-nfe/webhook/teste``)."""
        return cast(TesteWebhookEnfileirado, self._request("POST", f"{_MONITOR}/webhook/teste"))

    # ---------------------------------------------------- Emissão de NFS-e

    def criar_empresa_nfse(self, empresa: EmpresaNfseIn) -> EmpresaNfse:
        """Cadastra a empresa emissora (``POST /api/nfse/empresas``).

        Envie antes o certificado A1 da mesma raiz do CNPJ (``enviar_certificado_nfse``).
        """
        if not isinstance(empresa, Mapping) or not empresa:
            raise ValueError("Informe os dados da empresa.")
        return cast(EmpresaNfse, self._request("POST", f"{_NFSE}/empresas", json_body=empresa))

    def listar_empresas_nfse(self) -> List[EmpresaNfse]:
        """Empresas emissoras da conta, ativas e desativadas (``GET /api/nfse/empresas``)."""
        return cast(List[EmpresaNfse], self._request("GET", f"{_NFSE}/empresas", lista=True))

    def obter_empresa_nfse(self, empresa_id: str) -> EmpresaNfse:
        """Uma empresa emissora (``GET /api/nfse/empresas/{empresa_id}``)."""
        return cast(EmpresaNfse, self._get(f"{_NFSE}/empresas/{_id(empresa_id, 'empresa_id')}", {}))

    def atualizar_empresa_nfse(self, empresa_id: str, mudancas: EmpresaNfsePatch) -> EmpresaNfse:
        """Edita a empresa (``PATCH /api/nfse/empresas/{empresa_id}``): mande só o que muda.

        ``{"ativa": False}`` desliga a empresa; ``{"ativa": True}`` religa.
        """
        if not isinstance(mudancas, Mapping) or not mudancas:
            raise ValueError("Informe ao menos um campo em mudancas.")
        caminho = f"{_NFSE}/empresas/{_id(empresa_id, 'empresa_id')}"
        return cast(EmpresaNfse, self._request("PATCH", caminho, json_body=mudancas))

    def enviar_certificado_nfse(
        self,
        certificado: Certificado,
        *,
        senha: str = "",
        nome_arquivo: Optional[str] = None,
    ) -> CertificadoNfse:
        """Envia ou renova o certificado A1 da empresa (``PUT /api/nfse/certificados``, multipart).

        e-CNPJ ICP-Brasil, ``.pfx`` de até 100 KB, da mesma raiz do CNPJ que vai
        emitir. Substitui o anterior da mesma raiz. Não é repetido em 5xx.

        Args:
            certificado: caminho do arquivo, ``bytes`` do arquivo ou o conteúdo em base64.
            senha: senha do certificado (vazia se o ``.pfx`` não tiver).
            nome_arquivo: nome do arquivo no envio (padrão: o do caminho, ou ``certificado.pfx``).
        """
        pfx, nome = _certificado_bytes(certificado)
        corpo, tipo = _multipart(
            campos={"senha": senha or ""},
            arquivo=("certificado", nome_arquivo or nome, pfx, "application/x-pkcs12"),
        )
        return cast(
            CertificadoNfse,
            self._request("PUT", f"{_NFSE}/certificados", raw_body=corpo, content_type=tipo),
        )

    def excluir_certificado_nfse(self, raiz: str) -> None:
        """Exclui o certificado de uma raiz (``DELETE /api/nfse/certificados/{raiz}``).

        Aceita a raiz (8 caracteres) ou o CNPJ inteiro, com ou sem pontuação.
        Antes, desative as empresas da raiz.
        """
        limpa = "".join(c for c in (raiz or "") if c.isascii() and c.isalnum()).upper()
        if len(limpa) == 14:
            limpa = limpa[:8]
        if len(limpa) != 8:
            raise ValueError("Informe a raiz do CNPJ (8 caracteres) ou o CNPJ.")
        self._request("DELETE", f"{_NFSE}/certificados/{limpa}")

    def emitir_nfse(self, nota: NotaNfseIn, *, idempotency_key: Optional[str] = None) -> NotaNfse:
        """Pede a emissão de uma NFS-e (``POST /api/nfse/notas``).

        A resposta é ``202``, com a nota ``pendente``; o resultado chega pelo
        webhook ou por ``obter_nfse``. Em produção, mande ``referencia`` (ou
        ``idempotency_key``): o mesmo pedido devolve a nota que já existe. Com
        uma delas, o SDK repete a chamada em falha de rede e 5xx sem risco de
        nota em dobro.
        """
        if not isinstance(nota, Mapping) or not nota:
            raise ValueError("Informe os dados da nota.")
        chave = _chave_idempotencia(nota.get("referencia"), idempotency_key, nota.get("ambiente") == "producao")
        headers = {"Idempotency-Key": idempotency_key.strip()} if idempotency_key else None
        return cast(
            NotaNfse,
            self._request("POST", f"{_NFSE}/notas", json_body=nota, headers=headers, idempotent=chave is not None),
        )

    def obter_nfse(self, nota_id: str) -> NotaNfse:
        """Uma NFS-e emitida (``GET /api/nfse/notas/{nota_id}``)."""
        return cast(NotaNfse, self._get(f"{_NFSE}/notas/{_id(nota_id, 'nota_id')}", {}))

    def listar_nfse(
        self,
        *,
        status: Optional[StatusNotaNfse] = None,
        ambiente: Optional[AmbienteNfse] = None,
        referencia: Optional[str] = None,
        atualizada_desde: Optional[Union[str, datetime]] = None,
        cursor: Optional[str] = None,
        limite: Optional[int] = None,
    ) -> PaginaNotasNfse:
        """Uma página das NFS-e emitidas (``GET /api/nfse/notas``), em ordem de ``updated_at``.

        Args:
            status: só notas nesta situação.
            ambiente: ``"homologacao"`` ou ``"producao"``.
            referencia: busca pela sua referência.
            atualizada_desde: só notas com ``updated_at`` igual ou posterior. A nota
                do próprio instante volta de novo: trate a repetição pelo ``id``.
            cursor: ``proximo`` da página anterior.
            limite: notas por página, de 1 a 100 (padrão do servidor: 50).
        """
        if limite is not None and (isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 100):
            raise ValueError("limite deve ser um inteiro de 1 a 100.")
        desde = atualizada_desde.isoformat() if isinstance(atualizada_desde, datetime) else (atualizada_desde or None)
        params = {
            "status": status,
            "ambiente": ambiente,
            "referencia": referencia or None,
            "atualizada_desde": desde,
            "cursor": cursor or None,
            "limite": limite,
        }
        return cast(PaginaNotasNfse, self._get(f"{_NFSE}/notas", params))

    def iterar_nfse(
        self,
        *,
        status: Optional[StatusNotaNfse] = None,
        ambiente: Optional[AmbienteNfse] = None,
        referencia: Optional[str] = None,
        atualizada_desde: Optional[Union[str, datetime]] = None,
        limite: Optional[int] = None,
    ) -> Iterator[NotaNfse]:
        """Percorre todas as páginas da listagem, seguindo o cursor ``proximo``.

        Exemplo::

            for nota in api.iterar_nfse(ambiente="producao", atualizada_desde=ultimo):
                print(nota["id"], nota["status"])
        """
        cursor: Optional[str] = None
        while True:
            pagina = self.listar_nfse(
                status=status, ambiente=ambiente, referencia=referencia,
                atualizada_desde=atualizada_desde, cursor=cursor, limite=limite,
            )
            for nota in pagina.get("itens") or []:
                yield nota
            cursor = pagina.get("proximo")
            if not cursor:
                return

    def cancelar_nfse(self, nota_id: str, *, motivo: int, justificativa: str) -> NotaNfse:
        """Pede o cancelamento de uma NFS-e autorizada (``POST /api/nfse/notas/{nota_id}/cancelamento``).

        A resposta traz a nota ``cancelando``; o resultado chega pelo webhook
        (``cancelada`` ou ``cancelamento_recusado``).

        Args:
            motivo: ``1`` erro na emissão, ``2`` serviço não prestado, ``9`` outros.
            justificativa: de 15 a 255 caracteres.
        """
        texto = (justificativa or "").strip()
        if not 15 <= len(texto) <= 255:
            raise ValueError("justificativa deve ter de 15 a 255 caracteres.")
        caminho = f"{_NFSE}/notas/{_id(nota_id, 'nota_id')}/cancelamento"
        return cast(NotaNfse, self._request("POST", caminho, json_body={"motivo": motivo, "justificativa": texto}))

    def substituir_nfse(
        self,
        nota_id: str,
        substituicao: SubstituicaoNfseIn,
        *,
        idempotency_key: Optional[str] = None,
    ) -> NotaNfse:
        """Substitui uma NFS-e autorizada por outra (``POST /api/nfse/notas/{nota_id}/substituicao``).

        Devolve a nota NOVA, ``pendente``, com ``substitui_id``. Em produção,
        mande a ``referencia`` da nota nova (ou ``idempotency_key``).
        """
        if not isinstance(substituicao, Mapping) or not substituicao:
            raise ValueError("Informe os dados da substituição.")
        chave = _chave_idempotencia(substituicao.get("referencia"), idempotency_key, False)
        headers = {"Idempotency-Key": idempotency_key.strip()} if idempotency_key else None
        caminho = f"{_NFSE}/notas/{_id(nota_id, 'nota_id')}/substituicao"
        return cast(
            NotaNfse,
            self._request("POST", caminho, json_body=substituicao, headers=headers, idempotent=chave is not None),
        )

    def baixar_xml_nfse(self, nota_id: str) -> str:
        """XML da NFS-e autorizada (``GET /api/nfse/notas/{nota_id}/xml``). Não cobra."""
        caminho = f"{_NFSE}/notas/{_id(nota_id, 'nota_id')}/xml"
        conteudo = self._request("GET", caminho, binario=True, headers={"Accept": "application/xml"})
        return cast(bytes, conteudo).decode("utf-8")

    def baixar_pdf_nfse(self, nota_id: str) -> bytes:
        """PDF do DANFSe (``GET /api/nfse/notas/{nota_id}/pdf``). Não cobra."""
        caminho = f"{_NFSE}/notas/{_id(nota_id, 'nota_id')}/pdf"
        return cast(bytes, self._request("GET", caminho, binario=True, headers={"Accept": "application/pdf"}))

    def configurar_webhook_nfse(self, url: str) -> WebhookNfseConfigurado:
        """Configura o webhook da emissão (``PUT /api/nfse/webhook``).

        Um por conta, para os dois ambientes. O ``segredo`` volta só no primeiro
        cadastro: guarde-o. Chamar de novo troca a URL e mantém o segredo
        (``segredo`` ``None``).
        """
        url = (url or "").strip()
        if not url:
            raise ValueError("Informe a URL do webhook.")
        return cast(WebhookNfseConfigurado, self._request("PUT", f"{_NFSE}/webhook", json_body={"url": url}))

    def obter_webhook_nfse(self) -> WebhookNfse:
        """Webhook da emissão (``GET /api/nfse/webhook``). Sem webhook: ``url`` ``None``."""
        return cast(WebhookNfse, self._get(f"{_NFSE}/webhook", {}))

    def remover_webhook_nfse(self) -> None:
        """Remove o webhook da emissão (``DELETE /api/nfse/webhook``). As notas continuam."""
        self._request("DELETE", f"{_NFSE}/webhook")

    def reenviar_webhook_nfse(self, nota_id: str) -> ReenvioWebhookNfse:
        """Põe de novo na fila os avisos de uma nota (``POST /api/nfse/notas/{nota_id}/webhook``)."""
        caminho = f"{_NFSE}/notas/{_id(nota_id, 'nota_id')}/webhook"
        return cast(ReenvioWebhookNfse, self._request("POST", caminho))

    # ------------------------------------------------------- Imóvel rural

    def consultar_sigef(
        self, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> SigefResponse:
        """Parcelas certificadas no SIGEF/INCRA do detentor (``GET /api/consultar-sigef``)."""
        params = _um_documento(cpf=cpf, cnpj=cnpj)
        return cast(SigefResponse, self._get("/api/consultar-sigef", params))

    def consultar_sigef_parcela(
        self, uuid: str, *, force_fresh: bool = False
    ) -> SigefParcelaResponse:
        """Uma parcela SIGEF pelo UUID, com polígono, vértices e confrontantes
        (``GET /api/consultar-sigef-parcela``)."""
        if not uuid:
            raise ValueError("Informe o UUID da parcela.")
        params = {"uuid": uuid.strip(), "force_fresh": force_fresh or None}
        return cast(SigefParcelaResponse, self._get("/api/consultar-sigef-parcela", params))

    def consultar_cnir(
        self, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> CnirResponse:
        """Imóveis rurais no CNIR/CAFIR (``GET /api/consultar-cnir``)."""
        params = _um_documento(cpf=cpf, cnpj=cnpj)
        return cast(CnirResponse, self._get("/api/consultar-cnir", params))

    # ------------------------------------------------------------- Perfil

    def perfil_produtor(
        self, *, cpf: Optional[str] = None, cnpj: Optional[str] = None
    ) -> PerfilProdutorResponse:
        """Perfil consolidado do produtor rural (``GET /api/perfil-produtor``)."""
        params = _um_documento(cpf=cpf, cnpj=cnpj)
        return cast(PerfilProdutorResponse, self._get("/api/perfil-produtor", params))

    # ----------------------------------------------------------- Transporte

    def _get(self, path: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request("GET", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        content_type: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        idempotent: Optional[bool] = None,
        binario: bool = False,
        lista: bool = False,
    ) -> Any:
        url = self.base_url + path
        query = _encode_query(params or {})
        if query:
            url = f"{url}?{query}"

        data: Optional[bytes] = None
        req_headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if json_body is not None:
            data = json.dumps(json_body, default=_json_default).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            data = raw_body
            req_headers["Content-Type"] = content_type or "application/octet-stream"
        if headers:
            req_headers.update(headers)

        repete = method == "GET" or idempotent is True
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                if binario:
                    return raw
                return _decode_success(raw, lista=lista)
            except urllib.error.HTTPError as exc:
                status = exc.code
                resp_headers = dict(exc.headers.items()) if exc.headers else {}
                try:
                    raw_err = exc.read()
                except OSError:
                    raw_err = b""
                retryable = (status in _RETRYABLE_ANY_METHOD and b"NFSE_HOMOLOG_LIMITE" not in raw_err) or (
                    repete and status in _RETRYABLE_IDEMPOTENT
                )
                if retryable and attempt < self.max_retries:
                    time.sleep(_delay(attempt, resp_headers.get("Retry-After")))
                    attempt += 1
                    continue
                raise _error_from_response(status, raw_err, resp_headers) from None
            except OSError as exc:  # URLError, timeout, conexão recusada
                if repete and attempt < self.max_retries:
                    time.sleep(_delay(attempt, None))
                    attempt += 1
                    continue
                raise APIConnectionError(f"Falha ao conectar à FiscalAPI: {exc}") from exc


# ---------------------------------------------------------------- utilitários


def _um_documento(**docs: Optional[str]) -> Dict[str, str]:
    informados = {k: v.strip() for k, v in docs.items() if v is not None and v.strip()}
    nomes = " ou ".join(docs.keys())
    if not informados:
        raise ValueError(f"Informe {nomes}.")
    if len(informados) > 1:
        raise ValueError(f"Informe apenas um: {nomes}.")
    return informados


def _uf(uf: str) -> str:
    if not uf or len(uf.strip()) != 2:
        raise ValueError("Informe a UF com 2 letras (ex.: MT).")
    return uf.strip().upper()


def _lote(chaves: Sequence[Any]) -> Sequence[Any]:
    if isinstance(chaves, str) or not chaves:
        raise ValueError("Informe as chaves em lista, ex.: [\"3526...\"].")
    if len(chaves) > MONITOR_NFE_MAX_LOTE:
        raise ValueError(f"Envie no máximo {MONITOR_NFE_MAX_LOTE} chaves por chamada.")
    return chaves


def _chave_nfe(chave: str) -> str:
    """Chave de NF-e só com dígitos (tira pontos, espaços e o prefixo "NFe")."""
    digitos = "".join(c for c in (chave or "") if c.isascii() and c.isdigit())
    if not digitos:
        raise ValueError("Informe a chave de acesso.")
    return digitos


def _query_listagem(
    status: Optional[str],
    ativo: Optional[bool],
    alterado_desde: Optional[Union[str, datetime]],
    cursor: Optional[str],
    limite: Optional[int],
) -> Dict[str, Any]:
    if limite is not None and (isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 1000):
        raise ValueError("limite deve ser um inteiro de 1 a 1.000.")
    desde = alterado_desde.isoformat() if isinstance(alterado_desde, datetime) else (alterado_desde or None)
    return {"status": status, "ativo": ativo, "alterado_desde": desde, "cursor": cursor or None, "limite": limite}


def _encode_query(params: Mapping[str, Any]) -> str:
    clean = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        clean.append((key, str(value)))
    return urllib.parse.urlencode(clean)


def _certificado_base64(cert: Certificado) -> str:
    if isinstance(cert, (bytes, bytearray)):
        return base64.b64encode(bytes(cert)).decode("ascii")
    if isinstance(cert, os.PathLike):
        with open(cert, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")
    if isinstance(cert, str):
        try:
            is_file = len(cert) < 4096 and os.path.isfile(cert)
        except (OSError, ValueError):
            is_file = False
        if is_file:
            with open(cert, "rb") as fh:
                return base64.b64encode(fh.read()).decode("ascii")
        return "".join(cert.split())  # já está em base64
    raise TypeError("certificado deve ser caminho, bytes ou string base64.")


def _id(valor: str, nome: str) -> str:
    """Id (UUID) de empresa ou nota, pronto para o caminho."""
    v = (valor or "").strip() if isinstance(valor, str) else str(valor or "").strip()
    if not v:
        raise ValueError(f"Informe {nome}.")
    return urllib.parse.quote(v, safe="")


def _chave_idempotencia(referencia: Any, idempotency_key: Optional[str], producao: bool) -> Optional[str]:
    """Confere ``referencia`` x ``Idempotency-Key`` antes de chamar (a API responderia 422)."""
    ref = referencia.strip() if isinstance(referencia, str) else ""
    key = (idempotency_key or "").strip()
    if ref and key and ref != key:
        raise ValueError("referencia e idempotency_key diferentes: mande só uma, ou as duas iguais.")
    if producao and not ref and not key:
        raise ValueError("Em produção, informe referencia (ou idempotency_key) para não emitir a nota em dobro.")
    return ref or key or None


def _json_default(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    raise TypeError(f"Valor não serializável em JSON: {type(valor).__name__}")


def _certificado_bytes(cert: Certificado) -> Tuple[bytes, str]:
    """Bytes do .pfx e o nome do arquivo (caminho, bytes ou base64)."""
    if isinstance(cert, (bytes, bytearray)):
        dados, nome = bytes(cert), "certificado.pfx"
    elif isinstance(cert, os.PathLike) or (
        isinstance(cert, str) and len(cert) < 4096 and _arquivo_existe(cert)
    ):
        with open(cert, "rb") as fh:
            dados = fh.read()
        nome = os.path.basename(os.fspath(cert)) or "certificado.pfx"
    elif isinstance(cert, str):
        try:
            dados = base64.b64decode("".join(cert.split()), validate=True)
        except ValueError as exc:
            raise ValueError("certificado deve ser caminho, bytes ou string base64.") from exc
        nome = "certificado.pfx"
    else:
        raise TypeError("certificado deve ser caminho, bytes ou string base64.")
    if not dados:
        raise ValueError("Informe o certificado (.pfx).")
    return dados, nome


def _arquivo_existe(caminho: str) -> bool:
    try:
        return os.path.isfile(caminho)
    except (OSError, ValueError):
        return False


def _multipart(campos: Mapping[str, str], arquivo: Tuple[str, str, bytes, str]) -> Tuple[bytes, str]:
    """Corpo multipart/form-data (só biblioteca padrão)."""
    fronteira = f"fiscalapi-{_uuid.uuid4().hex}"
    partes: List[bytes] = []
    for nome, valor in campos.items():
        partes.append(
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n'.encode("utf-8")
            + valor.encode("utf-8")
            + b"\r\n"
        )
    campo, nome_arquivo, dados, tipo = arquivo
    nome_seguro = nome_arquivo.replace('"', "").replace("\r", "").replace("\n", "")
    partes.append(
        (
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{campo}"; filename="{nome_seguro}"\r\n'
            f"Content-Type: {tipo}\r\n\r\n"
        ).encode("utf-8")
        + dados
        + b"\r\n"
    )
    partes.append(f"--{fronteira}--\r\n".encode("ascii"))
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


def _delay(attempt: int, retry_after: Optional[str]) -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), _MAX_RETRY_AFTER)
        except ValueError:
            pass
    base = min(_MAX_BACKOFF, 0.5 * (2 ** attempt))
    return base + random.uniform(0, base / 4)


def _decode_success(raw: bytes, *, lista: bool = False) -> Any:
    if not raw:
        return [] if lista else {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FiscalAPIError("Resposta da API não é JSON válido.", body=raw[:500]) from exc
    if lista and isinstance(decoded, list):
        return decoded
    return decoded if isinstance(decoded, dict) else {"data": decoded}


def _error_from_response(status: int, raw: bytes, headers: Mapping[str, str]) -> FiscalAPIError:
    body: Any
    try:
        body = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = raw.decode("utf-8", errors="replace")[:500]

    code: Optional[str] = None
    message = f"Erro HTTP {status}"
    request_id: Optional[str] = None
    if isinstance(body, dict):
        code = body.get("error") or body.get("title")
        detail = body.get("message") or body.get("detail")
        if isinstance(detail, str) and detail:
            message = detail
        elif isinstance(detail, list) and detail:
            message = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
        request_id = body.get("request_id") or None
    elif isinstance(body, str) and body:
        message = body

    kwargs = dict(status_code=status, code=code, request_id=request_id, body=body, headers=headers)
    if status in (401, 403):
        return AuthenticationError(message, **kwargs)
    if status == 402:
        return InsufficientBalanceError(message, **kwargs)
    if status == 429:
        return RateLimitError(message, **kwargs)
    if status >= 500:
        return ServerError(message, **kwargs)
    if 400 <= status < 500:
        return BadRequestError(message, **kwargs)
    return FiscalAPIError(message, **kwargs)
