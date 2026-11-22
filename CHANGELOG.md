# Changelog

As versões seguem [SemVer](https://semver.org/lang/pt-BR/). Cada tag `vX.Y.Z` publica o pacote no PyPI.

## 0.7.0 (2026-11-22)

- Emissão de NFS-e Nacional (`/api/nfse`):
  - empresas: `criar_empresa_nfse`, `listar_empresas_nfse`, `obter_empresa_nfse`, `atualizar_empresa_nfse`;
  - certificado A1 em multipart: `enviar_certificado_nfse`, `excluir_certificado_nfse`;
  - notas: `emitir_nfse` (com `referencia` ou `idempotency_key`), `obter_nfse`, `listar_nfse` e `iterar_nfse` (cursor), `cancelar_nfse`, `substituir_nfse`, `baixar_xml_nfse`, `baixar_pdf_nfse`;
  - webhook: `configurar_webhook_nfse`, `obter_webhook_nfse`, `remover_webhook_nfse`, `reenviar_webhook_nfse`.
- Tipos da emissão (`NotaNfseIn`, `NotaNfse`, `EmpresaNfse`, `AvisoWebhookNfse` etc.). `Decimal` e `date` no corpo viram texto.
- `verificar_assinatura` vale também para os avisos da emissão (mesmo esquema do Monitor de NF-e).
- `emitir_nfse` e `substituir_nfse` com chave de idempotência são repetidos em falha de rede e `5xx`; o `429` `NFSE_HOMOLOG_LIMITE` não é repetido.

## 0.6.0 (2026-11-21)

- Monitor de NF-e por chave (cadastro, listagem, detalhe e webhook) e `verificar_assinatura`.
