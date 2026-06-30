# Security Notes

Implemented:

- HTTP-only JWT session cookies.
- OTP expiry, attempt limit, resend cooldown, and auth rate limiting.
- Organization-scoped dependencies and role capability checks.
- Encrypted provider keys at rest.
- Backend-mediated S3 uploads and server-side checksum verification.
- Extension/MIME validation and upload size limits.
- Audit logs for sensitive operations.
- Document/category access rules in retrieval queries.
- Retrieved text is treated as untrusted evidence, not system instructions.
- Security response headers and CORS scoping.

Remaining production work:

- Add database RLS policies, not just RLS enablement.
- Use AWS KMS or a managed secrets service for encryption keys.
- Add ClamAV or managed malware scanning before indexing.
- Add OCR for scanned PDFs if required.
- Add full CSRF protection if cookie-authenticated unsafe routes are exposed cross-site.
- Add WAF, TLS, private subnets, image scanning, and managed observability.
- Perform penetration testing and threat modeling before handling regulated data.
