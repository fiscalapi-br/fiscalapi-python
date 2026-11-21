"""Tipos (TypedDict) das respostas mais usadas da FiscalAPI.

As respostas são dicionários comuns; estes tipos servem para autocompletar no
editor e para checagem estática. Campos novos podem aparecer sem aviso — o
SDK não descarta nada do que a API devolve.
"""
from __future__ import annotations

from typing import List, Literal, Optional, TypedDict

StatusFonte = Literal["success", "error", "timeout", "skipped"]
StatusCertidao = Literal[
    "negativa",
    "positiva",
    "positiva_com_efeitos_de_negativa",
    "nao_contribuinte",
    "sem_certidao",
    "erro",
]


class SourceStatus(TypedDict, total=False):
    status: StatusFonte
    error_code: str
    error_message: str


class CnaeSecundario(TypedDict, total=False):
    codigo: str
    descricao: str


class InscricaoEstadual(TypedDict, total=False):
    inscricao_estadual: str
    razao_social: str
    nome_fantasia: str
    situacao_ie: str
    uf_ie: str
    tipo_ie: str
    logradouro: str
    complemento: str
    bairro: str
    numero: str
    municipio: str
    municipio_ibge: str
    cep: str
    regime_pagamento: str
    data_situacao: str
    situacao_contribuinte: str
    data_inicio_atividade: str
    cnae_codigo: str
    cnae_descricao: str
    regime_apuracao_icms: str
    situacao_nfe: str
    cpf_cnpj: str
    situacao_cadastral: str
    cnaes_secundarios: Optional[List[CnaeSecundario]]


class ConsultaIEResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    uf: str
    cached: bool
    results: List[InscricaoEstadual]


class IEPorUF(TypedDict, total=False):
    uf: str
    source_status: SourceStatus
    results: List[InscricaoEstadual]


class ConsultaIETodosResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    cached_ufs: List[str]
    results: List[IEPorUF]
    complete: bool


class CNPJResult(TypedDict, total=False):
    razao_social: str
    nome_fantasia: str
    situacao_cadastral: str
    data_situacao_cadastral: str
    cnae_principal_codigo: str
    cnae_principal_descricao: str
    cnaes_secundarios: List[dict]
    natureza_juridica: str
    capital_social: str
    endereco: dict
    qsa: List[dict]
    porte: str


class CNPJResponse(TypedDict, total=False):
    request_id: str
    cnpj: str
    cached: bool
    source_status: SourceStatus
    result: Optional[CNPJResult]


class Certidao(TypedDict, total=False):
    status: StatusCertidao
    status_raw: str
    validade: str
    validade_iso: str
    emissao: str
    emissao_iso: str
    protocolo: str
    pdf_base64: str
    url_verificacao: str
    codigo_autenticacao: str


class CNDResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    uf: str
    cached: bool
    source_status: SourceStatus
    result: Optional[Certidao]


class CNDPorUF(TypedDict, total=False):
    uf: str
    source_status: SourceStatus
    result: Optional[Certidao]


class CNDTodosResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    results: List[CNDPorUF]


class CertidaoFederal(Certidao, total=False):
    tipo: Literal["cndt", "cnd_federal", "crf_fgts"]
    orgao: str
    modo: Literal["consulta", "emissao"]


class CertidaoFederalResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    cached: bool
    source_status: SourceStatus
    result: Optional[CertidaoFederal]


class CertidoesTodasResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    cnd_estaduais: Optional[CNDTodosResponse]
    certidoes_federais: List[CertidaoFederalResponse]


class NfeXmlResultado(TypedDict, total=False):
    chave: str
    status: str
    cstat: str
    mensagem: str
    from_cache: bool
    manifestacao: Optional[str]
    xml: Optional[str]


class NfeXmlResponse(TypedDict, total=False):
    request_id: str
    total: int
    com_dado: int
    creditos_cobrados: int
    resultados: List[NfeXmlResultado]


class CteXmlResponse(TypedDict, total=False):
    request_id: str
    chave: str
    status: Literal["ok", "nao_autorizado", "nao_encontrado", "erro"]
    xml: Optional[str]  # cteProc completo, só com status "ok"
    mensagem: str
    creditos_cobrados: int


# DIFAL de saída (Beta). Só "paga" quita; sem_guia_no_portal,
# pendente_pagamento e geracao_rejeitada somam em valor_em_aberto, menos em
# DF, GO e MT: lá a guia é emitida no sistema da SEFAZ e sem_guia_no_portal
# soma em valor_a_conferir.
SituacaoGuiaDifal = Literal[
    "sem_guia_no_portal",
    "pendente_pagamento",
    "paga",
    "geracao_rejeitada",
    "aguardando_processamento",
    "substituida",
    "guia_gerada",
    "nao_se_aplica",
    "desconhecida",
]
# ok é cobrada; parcial, erro e nao_consultada não são.
StatusUfDifal = Literal["ok", "parcial", "erro", "nao_consultada"]


class NotaDifal(TypedDict, total=False):
    serie: str
    numero: str
    data_emissao: Optional[str]  # AAAA-MM-DD
    vencimento: Optional[str]  # vencimento do imposto, AAAA-MM-DD
    destinatario: str
    uf_destino: str
    valor_total: Optional[float]
    valor_difal: Optional[float]
    valor_fcp: Optional[float]
    situacao_guia_difal: SituacaoGuiaDifal
    situacao_guia_fcp: SituacaoGuiaDifal
    em_aberto: bool  # sem guia no portal (menos em DF, GO e MT), guia pendente ou rejeitada
    valor_em_aberto: float
    a_conferir: bool  # guia sem pagamento confirmado ou, em DF, GO e MT, sem guia no portal; fora do em aberto
    valor_a_conferir: float


class GuiaDifal(TypedDict, total=False):
    numero: str
    vencimento_imposto: Optional[str]
    data_limite_pagamento: Optional[str]
    uf: str
    tributo: str
    valor: Optional[float]
    situacao: Optional[str]  # paga | pendente_pagamento | geracao_rejeitada | aguardando_processamento | substituida


class UfDifalResultado(TypedDict, total=False):
    uf: str
    status: StatusUfDifal
    mensagem: str
    total_documentos: int
    valor_difal: float
    valor_fcp: float
    valor_em_aberto: float
    notas_em_aberto: int
    valor_a_conferir: float
    notas_a_conferir: int
    notas: List[NotaDifal]
    guias: List[GuiaDifal]


class DifalSaidaResponse(TypedDict, total=False):
    request_id: str
    fonte: str
    emitente_tipo: str  # CNPJ ou CPF do titular do certificado
    emitente_documento: str
    competencia: str  # AAAA-MM
    periodo_inicio: str
    periodo_fim: str
    total_documentos: int
    valor_difal: float
    valor_fcp: float
    valor_em_aberto: float
    notas_em_aberto: int
    valor_a_conferir: float
    notas_a_conferir: int
    completo: bool  # True só quando todas as UFs pedidas vieram "ok"
    ufs: List[UfDifalResultado]
    avisos: List[str]
    creditos_cobrados: int  # 1 por UF "ok"


class SigefParcela(TypedDict, total=False):
    parcel_id: str
    codigo_parcela: str
    denominacao: str
    area_ha: float
    municipio: str
    uf: str
    codigo_ibge: str
    detentor: str
    matricula: str
    cns: str
    status: str
    data_certificacao: str
    natureza: str
    codigo_sncr: str
    cartorio: str
    geometria_wkt: str
    vertices: List[dict]
    confrontantes: List[dict]


class SigefResult(TypedDict, total=False):
    total_parcelas: int
    area_total_ha: float
    parcelas: List[SigefParcela]


class SigefResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    cached: bool
    source_status: SourceStatus
    result: Optional[SigefResult]


class SigefParcelaResponse(TypedDict, total=False):
    request_id: str
    parcel_id: str
    cached: bool
    consultado_em: str
    completo: bool
    avisos: List[str]
    source_status: SourceStatus
    result: Optional[SigefParcela]


class CnirResponse(TypedDict, total=False):
    request_id: str
    document: str
    document_type: str
    source_status: SourceStatus
    pessoa_fisica: Optional[dict]
    pessoa_juridica: Optional[dict]
    imoveis_cafir: List[dict]
    total_imoveis: int
    total_imoveis_ativos: int


class PerfilProdutorResponse(TypedDict, total=False):
    request_id: str
    document: str
    receita_federal: Optional[CNPJResponse]
    inscricoes_estaduais: Optional[ConsultaIETodosResponse]
    cnd_estaduais: Optional[CNDTodosResponse]
    certidoes_federais: List[CertidaoFederalResponse]
    cnir: Optional[CnirResponse]


class SimplesNacionalEventoFuturo(TypedDict, total=False):
    regime: str
    descricao: str
    data_efeito: str


class SimplesNacionalPeriodoAnterior(TypedDict, total=False):
    data_inicial: str
    data_final: str
    detalhamento: str


class SimplesNacionalMaisInfo(TypedDict, total=False):
    opcoes_periodos_anteriores: str
    opcoes_periodos_anteriores_lista: List[SimplesNacionalPeriodoAnterior]
    enquadramentos_simei_periodos_anteriores: str
    enquadramentos_simei_periodos_anteriores_lista: List[SimplesNacionalPeriodoAnterior]
    eventos_futuros_simples: str
    eventos_futuros_simei: str
    mei_tac: str


class SimplesNacionalResponse(TypedDict, total=False):
    request_id: str
    cnpj: str
    cnpj_matriz: str  # para filiais, a situação é a da matriz
    nome_empresarial: str
    data_consulta: str
    situacao_simples: str
    optante_simples: bool
    data_opcao_simples: Optional[str]
    situacao_simei: str
    enquadrado_simei: bool
    regime_regular_ibs: str
    regime_regular_cbs: str
    eventos_futuros: List[SimplesNacionalEventoFuturo]
    mais_info: Optional[SimplesNacionalMaisInfo]
    cached: bool


class NfseEndereco(TypedDict, total=False):
    logradouro: Optional[str]
    numero: Optional[str]
    complemento: Optional[str]
    bairro: Optional[str]
    cep: Optional[str]
    municipio: Optional[str]
    uf: Optional[str]


class NfseEmitente(TypedDict, total=False):
    razao_social: Optional[str]
    cpf_cnpj: Optional[str]
    inscricao_municipal: Optional[str]
    situacao_simples_nacional: Optional[str]
    regime_especial_tributacao: Optional[str]
    endereco: Optional[NfseEndereco]


class NfsePessoa(TypedDict, total=False):
    cpf_cnpj: Optional[str]
    inscricao_municipal: Optional[str]
    nome: Optional[str]


class NfseServico(TypedDict, total=False):
    pais: Optional[str]
    municipio: Optional[str]
    codigo_tributacao_nacional: Optional[str]
    descricao_codigo: Optional[str]
    item_nbs: Optional[str]
    descricao: Optional[str]


class NfseTributacaoMunicipal(TypedDict, total=False):
    tributacao_issqn: Optional[str]
    municipio_incidencia: Optional[str]
    valor_servico: Optional[float]
    desconto_incondicionado: Optional[float]
    deducoes: Optional[float]
    beneficio_municipal: Optional[float]
    base_calculo: Optional[float]
    aliquota: Optional[float]  # percentual (2.5 = 2,5%)
    valor_issqn: Optional[float]
    retencao: Optional[str]


class NfseTributacaoFederal(TypedDict, total=False):
    situacao_pis_cofins: Optional[str]
    base_calculo_pis_cofins: Optional[float]
    aliquota_pis: Optional[float]
    valor_pis: Optional[float]
    aliquota_cofins: Optional[float]
    valor_cofins: Optional[float]
    irrf: Optional[float]
    contribuicoes_sociais_retidas: Optional[float]
    contribuicao_previdenciaria_retida: Optional[float]


class NfseResponse(TypedDict, total=False):
    request_id: str
    chave: str
    numero_nfse: Optional[str]
    codigo_municipio_emissor: Optional[str]
    data_geracao: Optional[str]
    versao: Optional[str]
    dps: Optional[dict]
    situacao: Optional[dict]  # codigo/descricao; não indica cancelamento
    emitente: Optional[NfseEmitente]
    tomador: Optional[NfsePessoa]
    intermediario: Optional[NfsePessoa]
    servico: Optional[NfseServico]
    tributacao_municipal: Optional[NfseTributacaoMunicipal]
    tributacao_federal: Optional[NfseTributacaoFederal]
    total_tributos: List[dict]
    informacoes_complementares: Optional[str]
    ambiente_gerador: Optional[str]
    cached: bool
    danfse_pdf_base64: Optional[str]  # só com danfse=True
    aviso: Optional[str]


# ---------------------------------------------------------- Monitor de NF-e

StatusMonitorNfe = Literal[
    "autorizada",
    "autorizada_fora_prazo",
    "denegada",
    "cancelada",
    "cancelada_fora_prazo",
    "nao_encontrada",
    "chave_divergente",
]


class ChaveParaMonitorar(TypedDict, total=False):
    chave: str
    status_conhecido: StatusMonitorNfe  # padrão "autorizada"


class ResultadoCadastroMonitor(TypedDict, total=False):
    chave: str
    situacao: Literal["aceita", "ja_monitorada", "invalida"]
    motivo: Optional[str]
    encerra_em: Optional[str]


class CadastroMonitorResponse(TypedDict, total=False):
    resultados: List[ResultadoCadastroMonitor]
    aceitas: int
    valor_cobrado: str  # em reais, ex.: "0,03"


class RemoverMonitorResponse(TypedDict, total=False):
    removidas: int
    nao_encontradas: List[str]


class EventoNfeMonitorada(TypedDict, total=False):
    tipo: Literal["cancelamento", "carta_correcao", "epec", "outro"]
    codigo: str
    sequencia: int
    protocolo: Optional[str]
    registrado_em: Optional[str]
    texto: Optional[str]


class ChaveMonitorada(TypedDict, total=False):
    chave: str
    status: Optional[StatusMonitorNfe]
    ativo: bool
    criada_em: str
    encerra_em: str
    encerrada_em: Optional[str]
    motivo_encerramento: Optional[str]
    ultima_verificacao_em: Optional[str]
    proxima_verificacao_em: Optional[str]
    atualizada_em: str
    entregas_falhas: int


class EntregaFalhaMonitor(TypedDict, total=False):
    id: str
    tipo: str
    criada_em: str
    tentativas: int
    ultimo_erro: Optional[str]


class ChaveMonitoradaDetalhe(ChaveMonitorada, total=False):
    eventos: List[EventoNfeMonitorada]
    entregas_que_falharam: List[EntregaFalhaMonitor]


class ListaChavesMonitoradas(TypedDict, total=False):
    itens: List[ChaveMonitorada]
    proximo_cursor: Optional[str]


class WebhookMonitorCriado(TypedDict, total=False):
    url: str
    segredo: str  # mostrado só aqui: guarde-o


class WebhookMonitorAtual(TypedDict, total=False):
    url: str
    ativo: bool
    falhando_desde: Optional[str]


class SegredoWebhookRotacionado(TypedDict, total=False):
    segredo: str
    anterior_valido_ate: str


class TesteWebhookEnfileirado(TypedDict, total=False):
    id: str
    estado: Literal["pendente"]
