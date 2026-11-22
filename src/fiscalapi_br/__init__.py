"""SDK oficial da FiscalAPI para Python.

Consulta de Inscrição Estadual, CNPJ, certidões, NF-e, CT-e, Monitor de NF-e,
emissão de NFS-e Nacional, SIGEF, CNIR e perfil do produtor rural pela API REST
https://api.fiscalapi.com.br.
"""
from ._client import DEFAULT_BASE_URL, MONITOR_NFE_MAX_LOTE, FiscalAPI
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
from .webhook import TOLERANCIA_PADRAO, verificar_assinatura

__all__ = [
    "DEFAULT_BASE_URL",
    "MONITOR_NFE_MAX_LOTE",
    "FiscalAPI",
    "TOLERANCIA_PADRAO",
    "verificar_assinatura",
    "FiscalAPIError",
    "AuthenticationError",
    "InsufficientBalanceError",
    "RateLimitError",
    "BadRequestError",
    "ServerError",
    "APIConnectionError",
    "__version__",
]
