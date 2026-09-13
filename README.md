# fiap_tech_challenge_oficina_auth_lambda

Function serverless de autenticação dos clientes via CPF e o API Gateway que funciona como porta de entrada de todo o sistema da oficina. Este é um dos 4 repositórios do Tech Challenge Fase 3:

| Repositório | Responsabilidade |
|---|---|
| `fiap_tech_challenge_oficina_api` | Aplicação principal, executando em Kubernetes |
| `fiap_tech_challenge_oficina_auth_lambda` | Este repositório. Function de autenticação via CPF e API Gateway |
| `fiap_tech_challenge_oficina_infra_k8s` | Terraform da rede, do cluster Kubernetes, do registro de imagens e do monitoramento |
| `fiap_tech_challenge_oficina_infra_database` | Terraform do banco de dados gerenciado |

## Tecnologias utilizadas

* Python 3.11
* AWS Lambda (imagem de container) e Amazon ECR
* Amazon API Gateway (HTTP API)
* PyJWT e psycopg2
* Terraform
* Datadog Lambda Extension
* GitHub Actions
* Pytest

## Como funciona

A função recebe `POST /auth` com o corpo `{"cpf": "..."}` e:

1. Valida o formato e os dígitos verificadores do CPF.
2. Consulta a tabela `cliente` no schema do ambiente (`dev` ou `prod`) do RDS e confere se o cliente existe e está com status `ativo`.
3. Gera um JWT HS256 assinado com o segredo do ambiente, o mesmo que a API usa para validar os tokens.

| Claim | Valor |
|---|---|
| `sub` | Id do cliente |
| `role` | `cliente` |
| `cpf` | CPF do cliente |
| `iat`, `nbf`, `exp` | Emissão e validade (padrão de 1 hora) |
| `jti`, `type`, `fresh` | Campos esperados pelo Flask-JWT-Extended da API |

| Status | Quando |
|---|---|
| `200` | CPF válido e cliente ativo, devolve `access_token`, `token_type` e `expires_in` |
| `400` | CPF inválido |
| `403` | Cliente inativo |
| `404` | Cliente não encontrado |

Os logs são em JSON e trazem o `correlation_id` (o requestId do API Gateway, também devolvido no header `X-Correlation-ID`). O CPF não é registrado nos logs. A conexão com o banco é reaproveitada entre invocações da mesma instância.

## API Gateway

Um HTTP API por ambiente (`oficina-gateway-dev` e `oficina-gateway-prod`):

| Rota | Destino |
|---|---|
| `POST /auth` | Esta Lambda |
| `ANY /{proxy+}` | LoadBalancer da API no Kubernetes, com o header `X-Correlation-ID` preenchido com o requestId |

* Throttling no stage, padrão de 50 requisições por segundo com rajada de 100
* Access logs em JSON no CloudWatch, com requestId, rota, status, latência e erro de integração
* A URL do gateway fica no output `gateway_url` e no parâmetro `/oficina/<env>/gateway_url`

Exemplo de uso:

```bash
curl -X POST https://<gateway>/auth -H "Content-Type: application/json" -d '{"cpf": "11144477735"}'
curl https://<gateway>/api/os -H "Authorization: Bearer <access_token>"
```

## Integração com os outros repositórios

Parâmetros lidos do AWS SSM Parameter Store:

| Parâmetro | Quem cria | Uso |
|---|---|---|
| `/oficina/network/vpc_id` e `/oficina/network/private_subnet_ids` | infra_k8s | A Lambda roda nas subnets privadas da VPC do cluster, onde está o RDS |
| `/oficina/db/*` | infra_database | Conexão com o banco |
| `/oficina/<env>/jwt_secret` | infra_k8s | Assinatura dos tokens |
| `/oficina/<env>/api_url` | pipeline da API | Destino da rota `ANY /{proxy+}` |

## Variáveis de ambiente da função

Configuradas pelo Terraform. Para rodar localmente, use o arquivo de exemplo:

```bash
cp .env.example .env
```

| Variável | Descrição |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Conexão com o PostgreSQL |
| `DB_SCHEMA` | Schema do ambiente, `dev` ou `prod` |
| `JWT_SECRET_KEY` | Segredo de assinatura, o mesmo da API no mesmo ambiente |
| `JWT_EXPIRACAO_SEGUNDOS` | Validade do token, padrão `3600` |
| `DD_API_KEY`, `DD_SITE`, `DD_ENV`, `DD_SERVICE`, `DD_VERSION` | Configuração da extensão do Datadog |

## Testes automatizados

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -v
```

Cobrem a validação de CPF e o handler completo com o banco simulado: CPF inválido, corpo inválido, cliente não encontrado, cliente inativo, claims do token gerado, propagação do correlation id e corpo em base64.

## Rodando a função localmente

A imagem base da AWS já traz o emulador do runtime do Lambda:

```bash
docker build --target base -t oficina-auth .
docker run --rm -p 9000:8080 --env-file .env oficina-auth
curl -X POST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"body": "{\"cpf\": \"11144477735\"}"}'
```

Com a API rodando localmente pelo Docker Compose, use `DB_HOST=host.docker.internal` no `.env` para a função enxergar o mesmo banco.

## Terraform

Os arquivos ficam em `terraform/` e usam a variável `env` (`dev` ou `prod`) para nomear e isolar os recursos de cada ambiente:

* Repositório ECR da imagem, com política que mantém as 10 imagens mais recentes
* IAM role da função, com permissão de rede na VPC e de escrita de logs
* Security group e configuração de VPC da função
* Função Lambda empacotada como imagem de container
* HTTP API, integrações, rotas, permissão de invocação e stage com throttling e access logs
* Log groups com retenção de 7 dias
* Parâmetro SSM com a URL do gateway

## CI/CD e ambientes

| Branch | Ambiente | Recursos |
|---|---|---|
| `dev` | dev | `oficina-auth-dev` e `oficina-gateway-dev` |
| `main` | prod | `oficina-auth-prod` e `oficina-gateway-prod` |

O pipeline em `.github/workflows/ci-cd.yml`:

| Job | Quando roda | O que faz |
|---|---|---|
| `test` | Pull requests para `main` ou `dev`, e pushes | Roda os testes, `terraform fmt` e `terraform validate` |
| `deploy` | Push em `dev` ou `main` | Garante o ECR, builda e envia a imagem (com a extensão do Datadog se houver API key), lê a URL da API no SSM e aplica o Terraform do ambiente |

Secrets necessários: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e, opcional, `DD_API_KEY`. Variáveis: `TF_STATE_BUCKET` (bucket S3 do estado do Terraform, o mesmo dos repos de infra), e opcionais `AWS_REGION` e `DD_SITE`. O estado de cada ambiente fica em `auth-lambda/<env>.tfstate`.

Este repositório deve ser o último no primeiro deploy, depois da API. Se for aplicado antes, o gateway sobe apenas com `POST /auth`, e a rota para a API passa a existir no próximo deploy.

## Documentação

O diagrama de sequência do fluxo de autenticação e o diagrama de arquitetura deste repositório serão adicionados aqui.

---
Este projeto faz parte do Tech Challenge da Pós Graduação em Arquitetura de Software da FIAP.
