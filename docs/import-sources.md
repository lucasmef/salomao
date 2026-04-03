# Fontes de Importacao

## OFX

Campos ja identificados no modelo atual:

- `TRNTYPE`
- `DTPOSTED`
- `TRNAMT`
- `FITID`
- `CHECKNUM`
- `REFNUM`
- `MEMO`
- `NAME`

## Template de cobrancas Inter

O template de cobrancas do Banco Inter deve ser baixado diretamente do portal oficial quando necessario.

- nao versionar a planilha baixada no repositorio
- usar apenas copias locais temporarias para validacao de layout e preenchimento

## Faturamento Linx

O arquivo atual e HTML exportado com extensao `.xls`.

Colunas relevantes:

- `Emissao`
- `Valor dos Documentos`
- `Dinheiro`
- `Ch.Vista`
- `Ch.Prazo`
- `Crediario`
- `Cartao`
- `Convenio`
- `Pix`
- `Financeiro`
- `Markup`
- `Desc/Acres`

## Faturas a Receber Linx

O arquivo atual tambem e HTML exportado com extensao `.xls`.

Colunas relevantes:

- `Emissao`
- `Fatura/Empresa`
- `Venc.`
- `Parc.`
- `Valor Fatura`
- `Valor c/Juros e Multa`
- `Cliente/Fornecedor`
- `Doc./Serie/Nosso Numero`
- `Status`

Observacao:

- existem linhas auxiliares com `Vendedor: ...`
- o importador deve ignorar linhas de grupo e linhas decorativas

## Status da implementacao atual

- importador de faturamento Linx operacional
- faturamento faz sobrescrita incremental por `dia`
- ao reimportar um ano, um mes ou alguns dias, somente as datas presentes no arquivo novo sao atualizadas
- importador de faturas a receber operacional
- importador OFX operacional
- deduplicacao por hash do arquivo importado
- deduplicacao de movimentos OFX por `conta + FITID`
