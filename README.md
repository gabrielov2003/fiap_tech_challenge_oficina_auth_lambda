# fiap_tech_challenge_oficina_auth_lambda

Lambda de autenticação dos clientes por CPF e o API Gateway, porta de entrada de todo o sistema. Faz parte do Tech Challenge Fase 4:

| Repositório | Responsabilidade |
|---|---|
| [fiap_tech_challenge_oficina_api](https://github.com/gabrielov2003/fiap_tech_challenge_oficina_api) | OS Service, orquestrador da Saga |
| [fiap_tech_challenge_oficina_billing_service](https://github.com/gabrielov2003/fiap_tech_challenge_oficina_billing_service) | Orçamentos e pagamentos com Mercado Pago |
| [fiap_tech_challenge_oficina_execution_service](https://github.com/gabrielov2003/fiap_tech_challenge_oficina_execution_service) | Fila de execução, diagnóstico e reparo |
| fiap_tech_challenge_oficina_auth_lambda | Este repositório. Autenticação por CPF e API Gateway |
| [fiap_tech_challenge_oficina_infra_k8s](https://github.com/gabrielov2003/fiap_tech_challenge_oficina_infra_k8s) | Rede, cluster EKS, registro de imagens, segredos e Datadog |
| [fiap_tech_challenge_oficina_infra_database](https://github.com/gabrielov2003/fiap_tech_challenge_oficina_infra_database) | Banco RDS PostgreSQL do OS Service |

## Arquitetura

```mermaid
flowchart LR
    C["Cliente"] -->|"POST /auth com CPF"| GW["API Gateway HTTP API"]
    GW -->|"invoca"| L["Lambda oficina-auth"]
    L -->|"REST com token de serviço"| OS["OS Service no EKS"]
    C -->|"/api, /billing e /execucao com JWT"| GW
    GW -->|"ANY /{proxy+}"| OS
    GW -->|"ANY /billing/{proxy+}"| B["Billing Service"]
    GW -->|"ANY /execucao/{proxy+}"| E["Execution Service"]
    L -.->|"logs"| CW["CloudWatch e Datadog"]
```

## Como funciona

`POST /auth` com `{"cpf": "..."}`:

1. Valida o formato e os dígitos do CPF.
2. Consulta o cliente no OS Service (`GET /api/clientes/documento/{cpf}`) com um token de serviço de 60 segundos e confere se está `ativo`. A Lambda não acessa o banco do OS Service, que é exclusivo dele.
3. Devolve um JWT HS256 assinado com a mesma chave que a API usa para validar.

| Status | Quando |
|---|---|
| `200` | Cliente ativo. Devolve `access_token`, `token_type` e `expires_in` |
| `400` | CPF inválido |
| `403` | Cliente inativo |
| `404` | Cliente não encontrado |

O token leva `sub` (id do cliente), `role` `cliente`, `cpf`, validade de 1 hora e os campos que o Flask-JWT-Extended da API espera (`jti`, `type` e `fresh`). Os logs são JSON com o `correlation_id`, que é o requestId do gateway e volta no header `X-Correlation-ID`. O CPF nunca vai para os logs.

```bash
curl -X POST https://<gateway>/auth -H "Content-Type: application/json" -d '{"cpf": "11144477735"}'
curl https://<gateway>/api/os -H "Authorization: Bearer <access_token>"
```

## API Gateway

Um HTTP API por ambiente (`oficina-gateway-dev` e `oficina-gateway-prod`), no stage `$default`:

| Rota | Destino |
|---|---|
| `POST /auth` | Esta Lambda |
| `ANY /{proxy+}` | LoadBalancer do OS Service, com `X-Correlation-ID` igual ao requestId |
| `ANY /billing/{proxy+}` | LoadBalancer do Billing Service, incluindo o webhook do Mercado Pago |
| `ANY /execucao/{proxy+}` | LoadBalancer do Execution Service |

Throttling de 50 requisições por segundo com rajada de 100, e access logs JSON no CloudWatch. A URL fica no output `gateway_url` e em `/oficina/<env>/gateway_url` no SSM. Os Swaggers ficam em `<URL do gateway>/apidocs/`, `/billing/apidocs/` e `/execucao/apidocs/`.

## Integração com os outros repositórios

| Parâmetro no SSM | Criado por | Uso |
|---|---|---|
| `/oficina/network/vpc_id` e `/oficina/network/private_subnet_ids` | infra_k8s | A Lambda roda nas subnets privadas e sai pelo NAT |
| `/oficina/<env>/jwt_secret` | infra_k8s | Assinatura dos tokens |
| `/oficina/<env>/api_url` | pipeline do OS Service | Rota `ANY /{proxy+}` e consulta do cliente |
| `/oficina/<env>/billing_url` | pipeline do Billing | Rota `ANY /billing/{proxy+}` |
| `/oficina/<env>/execucao_url` | pipeline do Execution | Rota `ANY /execucao/{proxy+}` |

## Testes e execução local

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -v
```

Os testes cobrem CPF inválido, corpo inválido, cliente não encontrado e inativo, claims do token, correlation id, corpo em base64 e a consulta ao OS Service (encontrado, não encontrado e fora do ar).

Para rodar a função no emulador da AWS, copie `.env.example` para `.env`. Com a API local no Docker Compose, use `API_URL=http://host.docker.internal:5000`:

```bash
docker build --target base -t oficina-auth .
docker run --rm -p 9000:8080 --env-file .env oficina-auth
curl -X POST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"body": "{\"cpf\": \"11144477735\"}"}'
```

## Terraform

Fica em `terraform/` e usa a variável `env` (`dev` ou `prod`) para nomear os recursos: ECR da imagem, IAM role, security group, Lambda em imagem de container dentro da VPC, HTTP API com as rotas dos três serviços, stage e access logs, log groups com 7 dias de retenção e o parâmetro com a URL do gateway. O estado de cada ambiente fica em `auth-lambda/<env>.tfstate`.

## CI/CD

| Branch | Ambiente | Recursos |
|---|---|---|
| `dev` | dev | `oficina-auth-dev` e `oficina-gateway-dev` |
| `main` | prod | `oficina-auth-prod` e `oficina-gateway-prod` |

| Job | Quando roda | O que faz |
|---|---|---|
| `test` | Pull requests e pushes em `dev` e `main` | Testes, `terraform fmt` e `terraform validate` |
| `deploy` | Push em `dev` ou `main` | Build da imagem (com a extensão do Datadog se houver API key), push no ECR e `terraform apply` do ambiente |

Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e, opcional, `DD_API_KEY`. Variáveis: `TF_STATE_BUCKET` e, opcionais, `AWS_REGION` e `DD_SITE`.

Este repositório é o último no primeiro deploy, depois dos três serviços. Se subir antes deles, o gateway fica só com as rotas que já existem até o próximo deploy.

## Documentação

RFCs, ADRs, diagramas e roteiro do vídeo: [documentacao_fase3](https://github.com/gabrielov2003/TechChallenge1/tree/main/documentacao_fase3).

---
Este projeto faz parte do Tech Challenge da Pós Graduação em Arquitetura de Software da FIAP.
