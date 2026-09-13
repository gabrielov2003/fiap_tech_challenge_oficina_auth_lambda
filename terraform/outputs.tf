output "gateway_url" {
  value = aws_apigatewayv2_api.gateway.api_endpoint
}

output "auth_url" {
  value = "${aws_apigatewayv2_api.gateway.api_endpoint}/auth"
}

output "function_name" {
  value = aws_lambda_function.auth.function_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.auth.repository_url
}

output "api_roteada" {
  value = var.api_url != ""
}
