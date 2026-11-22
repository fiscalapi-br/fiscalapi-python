"""Verificação da assinatura dos avisos do Monitor de NF-e e da Emissão de NFS-e
(o esquema é o mesmo nos dois produtos).

Cada aviso chega com ``X-FiscalAPI-Timestamp`` (segundos Unix) e
``X-FiscalAPI-Assinatura: v1=<hex>``, onde
``hex = HMAC-SHA256(segredo, f"{timestamp}." + corpo_bruto)`` e o segredo é a
string inteira ``whsec_...``. Na troca de segredo o cabeçalho traz
``v1=nova,v1=anterior`` por 24 h.

Exemplo (Flask)::

    from fiscalapi_br import verificar_assinatura

    @app.post("/fiscalapi/avisos")
    def avisos():
        ok = verificar_assinatura(
            request.get_data(),  # corpo bruto, antes de qualquer parse
            request.headers.get("X-FiscalAPI-Assinatura"),
            request.headers.get("X-FiscalAPI-Timestamp"),
            os.environ["FISCALAPI_WEBHOOK_SEGREDO"],
        )
        if not ok:
            return "", 401
        aviso = request.get_json()
        # deduplique: no monitor, por aviso["id"]; na emissão de NFS-e, por
        # X-FiscalAPI-Entrega + aviso["updated_at"] (entrega "pelo menos uma vez")
        return "", 200
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional, Union

TOLERANCIA_PADRAO = 300
"""Diferença máxima aceita entre o timestamp do aviso e o relógio local, em segundos."""

Corpo = Union[bytes, bytearray, memoryview, str]


def _bytes(corpo: Corpo) -> bytes:
    if isinstance(corpo, str):
        return corpo.encode("utf-8")
    return bytes(corpo)


def assinar(segredo: str, timestamp: Union[int, str], corpo: Corpo) -> str:
    """Hex da assinatura ``v1`` de um corpo: útil para testar seu receptor."""
    mensagem = f"{str(timestamp).strip()}.".encode("ascii") + _bytes(corpo)
    return hmac.new(segredo.encode("utf-8"), mensagem, hashlib.sha256).hexdigest()


def verificar_assinatura(
    corpo_bruto: Corpo,
    cabecalho_assinatura: Optional[str],
    cabecalho_timestamp: Optional[Union[str, int]],
    segredo: str,
    tolerancia: int = TOLERANCIA_PADRAO,
    *,
    agora: Optional[float] = None,
) -> bool:
    """Confere se um aviso do Monitor de NF-e ou da Emissão de NFS-e veio da FiscalAPI.

    Args:
        corpo_bruto: bytes do corpo exatamente como chegaram (não o JSON reserializado).
        cabecalho_assinatura: valor de ``X-FiscalAPI-Assinatura``.
        cabecalho_timestamp: valor de ``X-FiscalAPI-Timestamp``.
        segredo: segredo do webhook (``whsec_...``).
        tolerancia: diferença máxima aceita, em segundos (padrão 300; 0 desliga).
        agora: instante atual em segundos Unix (para testes).

    Returns:
        ``True`` só se alguma assinatura ``v1=`` bater e o timestamp estiver
        dentro da tolerância.
    """
    if not segredo or not cabecalho_assinatura or cabecalho_timestamp is None:
        return False
    ts = str(cabecalho_timestamp).strip()
    if not ts.isascii() or not ts.isdigit():
        return False
    momento = time.time() if agora is None else agora
    if tolerancia and tolerancia > 0 and abs(momento - int(ts)) > tolerancia:
        return False

    recebidas = [
        parte.strip()[3:].strip().lower()
        for parte in cabecalho_assinatura.split(",")
        if parte.strip().startswith("v1=")
    ]
    if not recebidas:
        return False
    esperada = assinar(segredo, ts, corpo_bruto).encode("ascii")
    ok = False
    for recebida in recebidas:
        # bytes: compare_digest recusa str fora do ASCII
        ok = hmac.compare_digest(esperada, recebida.encode("utf-8")) or ok
    return ok
