# C6 Sandbox

Configuracao inicial da integracao C6 focada apenas em consulta de boletos.

## O que foi preparado

- Cadastro de credenciais C6 por conta no ERP.
- Armazenamento criptografado de `client_secret`, certificado PEM e chave privada PEM.
- Teste de autenticacao mTLS no sandbox.
- Consulta de boleto C6 por `id`.
- Download do PDF do boleto consultado.

## Dados oficiais usados

- Auth sandbox: `https://baas-api-sandbox.c6bank.info/v1/auth`
- Boletos sandbox: `https://baas-api-sandbox.c6bank.info/v1/bank_slips`
- Grant type: `client_credentials`

Baseado nos YAMLs oficiais publicados em:

- [Autenticação](https://developers.c6bank.com.br/yamls/authentication-api.yaml)
- [Boleto Bancário](https://developers.c6bank.com.br/yamls/bankslip-api.yaml)

## Como preencher no sistema

Na tela de contas, habilite `API C6 Bank` e preencha:

- `Ambiente C6`: `sandbox`
- `Client ID C6`: o `ClientId` recebido no email
- `Nome do software`: nome que sera enviado no header `partner-software-name`
- `Versao do software`: versao enviada no header `partner-software-version`
- `Client secret C6`: o `ClientSecret` recebido
- `Certificado PEM C6`: conteudo do arquivo `.crt`
- `Chave privada PEM C6`: conteudo do arquivo `.key`

Os arquivos que voce recebeu ja estao em PEM:

- certificado: `-----BEGIN CERTIFICATE-----`
- chave: `-----BEGIN RSA PRIVATE KEY-----`

## Endpoints locais

- `POST /api/v1/boletos/c6/auth-test`
- `GET /api/v1/boletos/c6/{bank_slip_id}`
- `GET /api/v1/boletos/c6/{bank_slip_id}/pdf`

## Exemplos

Teste de autenticacao:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/boletos/c6/auth-test \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: SEU_TOKEN_DA_APP" \
  -d "{}"
```

Consultar boleto:

```bash
curl "http://127.0.0.1:8000/api/v1/boletos/c6/SEU_ID_DO_BOLETO" \
  -H "X-Auth-Token: SEU_TOKEN_DA_APP"
```

Baixar PDF:

```bash
curl "http://127.0.0.1:8000/api/v1/boletos/c6/SEU_ID_DO_BOLETO/pdf" \
  -H "X-Auth-Token: SEU_TOKEN_DA_APP" \
  --output boleto-c6.pdf
```

## Proximo passo operacional

Antes da homologacao final, ainda falta enviar o roteiro de conformidade para `homologacaoapi@c6bank.com`.
