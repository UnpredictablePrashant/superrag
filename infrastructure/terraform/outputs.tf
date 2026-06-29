output "s3_bucket_name" {
  value = module.rag_console_app.s3_bucket_name
}

output "kms_key_arn" {
  value = module.rag_console_app.kms_key_arn
}
