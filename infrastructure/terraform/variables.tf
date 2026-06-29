variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "rag-console"
}

variable "container_image" {
  type        = string
  description = "API and worker container image URI."
}

variable "web_image" {
  type        = string
  description = "Frontend container image URI."
}
