resource "aws_kms_key" "main" {
  description             = "RAG Console encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_s3_bucket" "documents" {
  bucket_prefix = "${var.name_prefix}-documents-"
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.main.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name_prefix}/api"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.name_prefix}/worker"
  retention_in_days = 30
}

# Starter placeholders. Production deployments should attach these to a VPC module,
# private subnets, security groups, an ALB, ECS/Fargate services, RDS PostgreSQL
# with pgvector enabled, ElastiCache Redis, and SES verified identities.
locals {
  required_runtime_components = [
    "ECS or Kubernetes service for web",
    "ECS or Kubernetes service for api",
    "ECS or Kubernetes service for worker",
    "RDS PostgreSQL with pgvector extension",
    "ElastiCache Redis",
    "Application Load Balancer with TLS",
    "SES verified sender/domain",
  ]
}
