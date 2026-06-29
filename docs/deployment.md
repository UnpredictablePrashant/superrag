# Deployment Guide

The Compose setup is for local development. A production AWS deployment should include:

- S3 bucket with versioning, KMS encryption, lifecycle policies, and access logs.
- RDS PostgreSQL with pgvector enabled.
- ElastiCache Redis for Celery broker/result backend and rate-limit storage.
- ECS/Fargate or Kubernetes workloads for web, API, and worker.
- Application Load Balancer with TLS.
- SES verified domain for OTP and invitations.
- CloudWatch logs, metrics, alarms, and traces.
- Secrets Manager or SSM Parameter Store for API keys and encryption secrets.

Terraform in `infrastructure/terraform` creates starter S3/KMS/CloudWatch resources and documents the remaining module boundaries.
