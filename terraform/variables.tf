variable "region" {
  description = "Região AWS"
  type        = string
  default     = "us-east-1"
}

variable "env" {
  description = "Ambiente do deploy: dev (branch dev) ou prod (branch main)"
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "O ambiente deve ser dev ou prod."
  }
}

variable "image_tag" {
  description = "Tag da imagem da Lambda no ECR, normalmente o SHA do commit"
  type        = string
}

variable "api_url" {
  description = "URL do LoadBalancer da API no Kubernetes, publicada pelo pipeline da API em /oficina/<env>/api_url"
  type        = string
  default     = ""
}

variable "jwt_expiracao_segundos" {
  description = "Validade do token JWT gerado para o cliente"
  type        = number
  default     = 3600
}

variable "memoria_mb" {
  description = "Memória da Lambda em MB"
  type        = number
  default     = 256
}

variable "throttling_burst" {
  description = "Limite de rajada de requisições no API Gateway"
  type        = number
  default     = 100
}

variable "throttling_rate" {
  description = "Limite de requisições por segundo no API Gateway"
  type        = number
  default     = 50
}

variable "datadog_api_key" {
  description = "API key do Datadog, habilita a extensão de monitoramento da Lambda"
  type        = string
  default     = ""
  sensitive   = true
}

variable "datadog_site" {
  description = "Site do Datadog da conta"
  type        = string
  default     = "datadoghq.com"
}
