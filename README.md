# fiap_tech_challenge_oficina_auth_lambda

Function serverless responsável pela autenticação dos clientes via CPF.

Responsabilidades:
* Validar o formato do CPF recebido.
* Consultar a existência e o status do cliente na base de dados da oficina.
* Gerar e devolver um token JWT válido para consumo das APIs protegidas do repositório `fiap_tech_challenge_oficina_api`.

Esta função fica atrás de um API Gateway, que roteia as requisições de autenticação até ela.

Este README será atualizado com tecnologias, instruções de execução e deploy, e diagrama de arquitetura conforme o desenvolvimento avançar.
