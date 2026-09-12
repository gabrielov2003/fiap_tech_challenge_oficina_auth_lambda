# fiap_tech_challenge_oficina_auth_lambda

Function serverless responsável pela autenticação dos clientes via CPF.

Responsabilidades:
* Validar o formato e o dígito verificador do CPF recebido.
* Consultar a existência do cliente na base de dados do repositório `fiap_tech_challenge_oficina_infra_database`.
* Gerar e devolver um token JWT válido para consumo das APIs protegidas do repositório `fiap_tech_challenge_oficina_api`.

Esta função fica atrás de um API Gateway, que roteia as requisições de autenticação até ela. O provisionamento do API Gateway e a conectividade entre esta função e o banco de dados serão definidos no próximo passo da Fase 3, quando a integração entre os repositórios for implementada.

## Tecnologias utilizadas

* Python 3.11
* PyJWT, geração do token JWT
* psycopg2, conexão com o PostgreSQL
* AWS Lambda (imagem de container), execução serverless
* Amazon ECR, registro da imagem
* GitHub Actions, pipeline de CI/CD
* Pytest, testes automatizados

## Como funciona

`lambda_function.lambda_handler` recebe o evento do API Gateway com um corpo `{"cpf": "..."}`, valida o CPF, consulta o cliente pela coluna `documento` na tabela `cliente`, e retorna um JWT assinado com o `id_cliente` e o CPF como claims.

Respostas:
* `200`, com o `access_token`, se o CPF for válido e o cliente existir
* `400`, se o CPF for inválido
* `404`, se o cliente não for encontrado

## Variáveis de ambiente

Copie o arquivo de exemplo e ajuste os valores conforme necessário:
```bash
cp .env.example .env
```

| Variável | Descrição |
|---|---|
| `DB_HOST` | Endereço do banco de dados gerenciado |
| `DB_PORT` | Porta do banco, padrão `5432` |
| `DB_NAME` | Nome do banco, padrão `oficina` |
| `DB_USER` | Usuário de conexão com o banco |
| `DB_PASSWORD` | Senha de conexão com o banco |
| `JWT_SECRET_KEY` | Chave secreta para assinar os tokens JWT, deve ser a mesma usada pelo repositório `fiap_tech_challenge_oficina_api` para validar os tokens |

## Testes automatizados

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -v
```

Os testes cobrem a validação de CPF: formato, dígito verificador, CPFs repetidos e entradas inválidas.

## Docker

A função é empacotada como imagem de container Lambda:
```bash
docker build -t oficina-auth-lambda .
```

## CI/CD

O pipeline em `.github/workflows/ci-cd.yml` roda em pull requests e a cada push em `main`:

| Job | O que faz |
|---|---|
| `test` | Instala dependências e roda os testes |
| `build-and-deploy` | Builda e envia a imagem para o ECR, e atualiza a função Lambda, roda apenas em push para `main` e se houver credenciais AWS configuradas |

Secrets necessários no GitHub (Settings, Secrets and variables, Actions):

| Secret | Descrição |
|---|---|
| `AWS_ACCESS_KEY_ID` | Chave de acesso da AWS |
| `AWS_SECRET_ACCESS_KEY` | Chave secreta da AWS |

Sem essas credenciais configuradas, o pipeline roda os testes normalmente e ignora a etapa de deploy.

## Documentação

O diagrama de sequência do fluxo de autenticação e o diagrama de arquitetura específico deste repositório serão adicionados aqui conforme a Fase 3 avança.

---
Este projeto faz parte do Tech Challenge da Pós Graduação em Arquitetura de Software da FIAP.
