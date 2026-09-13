terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      projeto  = "oficina"
      ambiente = var.env
    }
  }
}

locals {
  nome = "oficina-auth-${var.env}"
}

data "aws_ssm_parameter" "vpc_id" {
  name = "/oficina/network/vpc_id"
}

data "aws_ssm_parameter" "private_subnets" {
  name = "/oficina/network/private_subnet_ids"
}

data "aws_ssm_parameter" "db_host" {
  name = "/oficina/db/host"
}

data "aws_ssm_parameter" "db_port" {
  name = "/oficina/db/port"
}

data "aws_ssm_parameter" "db_name" {
  name = "/oficina/db/name"
}

data "aws_ssm_parameter" "db_username" {
  name = "/oficina/db/username"
}

data "aws_ssm_parameter" "db_password" {
  name = "/oficina/db/password"
}

data "aws_ssm_parameter" "jwt_secret" {
  name = "/oficina/${var.env}/jwt_secret"
}

resource "aws_ecr_repository" "auth" {
  name                 = local.nome
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "auth" {
  repository = aws_ecr_repository.auth.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Mantem apenas as 10 imagens mais recentes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

resource "aws_iam_role" "lambda" {
  name = local.nome

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_security_group" "lambda" {
  name        = local.nome
  description = "Saida da Lambda de autenticacao para o banco e para a internet"
  vpc_id      = data.aws_ssm_parameter.vpc_id.insecure_value

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.nome}"
  retention_in_days = 7
}

resource "aws_lambda_function" "auth" {
  function_name = local.nome
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.auth.repository_url}:${var.image_tag}"
  timeout       = 10
  memory_size   = var.memoria_mb

  vpc_config {
    subnet_ids         = split(",", data.aws_ssm_parameter.private_subnets.insecure_value)
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = merge({
      DB_HOST                = data.aws_ssm_parameter.db_host.value
      DB_PORT                = data.aws_ssm_parameter.db_port.value
      DB_NAME                = data.aws_ssm_parameter.db_name.value
      DB_USER                = data.aws_ssm_parameter.db_username.value
      DB_PASSWORD            = data.aws_ssm_parameter.db_password.value
      DB_SCHEMA              = var.env
      JWT_SECRET_KEY         = data.aws_ssm_parameter.jwt_secret.value
      JWT_EXPIRACAO_SEGUNDOS = tostring(var.jwt_expiracao_segundos)
      DD_ENV                 = var.env
      DD_SERVICE             = "oficina-auth"
      DD_VERSION             = var.image_tag
      DD_SITE                = var.datadog_site
    }, var.datadog_api_key == "" ? {} : { DD_API_KEY = var.datadog_api_key })
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_vpc, aws_cloudwatch_log_group.lambda]
}

resource "aws_apigatewayv2_api" "gateway" {
  name          = "oficina-gateway-${var.env}"
  protocol_type = "HTTP"
  description   = "Gateway de entrada da oficina, ambiente ${var.env}"
}

resource "aws_apigatewayv2_integration" "auth" {
  api_id                 = aws_apigatewayv2_api.gateway.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "auth" {
  api_id    = aws_apigatewayv2_api.gateway.id
  route_key = "POST /auth"
  target    = "integrations/${aws_apigatewayv2_integration.auth.id}"
}

resource "aws_apigatewayv2_integration" "api" {
  count = var.api_url == "" ? 0 : 1

  api_id             = aws_apigatewayv2_api.gateway.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = "${var.api_url}/{proxy}"

  request_parameters = {
    "overwrite:header.X-Correlation-ID" = "$context.requestId"
  }
}

resource "aws_apigatewayv2_route" "api" {
  count = var.api_url == "" ? 0 : 1

  api_id    = aws_apigatewayv2_api.gateway.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api[0].id}"
}

resource "aws_lambda_permission" "gateway" {
  statement_id  = "PermiteInvocacaoPeloGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.gateway.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/aws/apigateway/oficina-gateway-${var.env}"
  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "padrao" {
  api_id      = aws_apigatewayv2_api.gateway.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = var.throttling_burst
    throttling_rate_limit  = var.throttling_rate
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.gateway.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      path             = "$context.path"
      status           = "$context.status"
      responseLatency  = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_ssm_parameter" "gateway_url" {
  name  = "/oficina/${var.env}/gateway_url"
  type  = "String"
  value = aws_apigatewayv2_api.gateway.api_endpoint
}
