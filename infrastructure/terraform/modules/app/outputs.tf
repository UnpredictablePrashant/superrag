output "s3_bucket_name" {
  value = aws_s3_bucket.documents.bucket
}

output "kms_key_arn" {
  value = aws_kms_key.main.arn
}
