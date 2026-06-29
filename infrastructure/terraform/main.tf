terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

module "rag_console_app" {
  source = "./modules/app"

  name_prefix     = var.name_prefix
  aws_region      = var.aws_region
  container_image = var.container_image
  web_image       = var.web_image
}
