# EC2 Deployment

This deployment path builds the API and web Docker images in GitHub Actions, pushes them to GitHub Container Registry, installs Nginx and Certbot on the EC2 instance, configures path-based reverse proxy routing, and restarts the Docker Compose stack over SSH.

## EC2 prerequisites

- Docker Engine with the Docker Compose plugin installed.
- A DNS `A` record for `rag.atharvaai.com` pointing at the EC2 public IP `18.188.234.72`. Prefer an Elastic IP so the record stays stable.
- A security group that allows SSH from your IP and public web traffic on ports `80` and `443`.
- An application directory on the instance, defaulting to `/opt/rag-console`.
- An S3 bucket and email provider credentials for production uploads and OTP email.

The workflow installs Nginx, Certbot, and curl on the EC2 host. Nginx owns public ports `80` and `443`; Docker publishes the API and web containers only on localhost.

## GitHub configuration

Add these repository secrets:

- `EC2_SSH_KEY`: private SSH key that can connect to the instance.
- `DATABASE_URL`: production database URL. For the bundled EC2 Postgres service, use host `postgres`.
- `REDIS_URL`: production Redis URL. For the bundled EC2 Redis service, use `redis://redis:6379/0`.
- `JWT_SECRET`: random session-signing secret with at least 32 characters.
- `ENCRYPTION_KEY`: Fernet key used to encrypt provider credentials.
- `AWS_ACCESS_KEY_ID`: AWS access key for S3 and SES. The workflow maps this to both `S3_ACCESS_KEY_ID` and `AWS_ACCESS_KEY_ID` in the container env.
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key for S3 and SES. The workflow maps this to both `S3_SECRET_ACCESS_KEY` and `AWS_SECRET_ACCESS_KEY` in the container env.
- `S3_BUCKET`: S3 bucket name for document uploads.
- `S3_REGION`: S3 bucket region.
- `SES_EMAIL_FROM`: verified SES sender address, for example `RAG Console <no-reply@atharvaai.com>`.
- `SES_REGION`: SES region.
- `MAX_UPLOAD_BYTES`: optional upload limit. Defaults to `104857600`.
- `POSTGRES_PASSWORD`: optional. Add it when `DATABASE_URL` uses the bundled EC2 Postgres service and make sure both values use the same password.
- `TLS_EMAIL`: optional email address for Let's Encrypt certificate notices. If omitted, Certbot registers without an email address.
- `EC2_HOST`, `EC2_USER`, `EC2_APP_DIR`, and `EC2_PORT`: optional as secrets. They default to `18.188.234.72`, `ubuntu`, `/opt/rag-console`, and `22`.
- `EC2_ENV_FILE_B64`: optional alternative to the individual app secrets above. When set, the workflow writes this decoded file directly to EC2.
- `GHCR_TOKEN`: GitHub token with `read:packages` for pulling private GHCR images from EC2. Public packages can omit this.

Add these repository variables:

- `NEXT_PUBLIC_API_URL`: browser-facing API URL. Defaults to `https://rag.atharvaai.com/api`.
- `EC2_HOST`, `EC2_USER`, `EC2_APP_DIR`, and `EC2_PORT`: optional non-secret overrides if you prefer repository variables over repository secrets.

If you prefer the single bundled secret path, create and review the production env file:

```powershell
Copy-Item deploy\ec2\ec2.env.example .env.ec2.production
notepad .env.ec2.production
```

After replacing the placeholder values, encode it for the GitHub secret:

```powershell
$envText = Get-Content -Raw .env.ec2.production
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($envText))
```

Save the result as `EC2_ENV_FILE_B64`. If you use the individual secrets listed above, this bundled secret is not needed.

Generate a Fernet key for `ENCRYPTION_KEY` with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Deploy

Point `rag.atharvaai.com` at the EC2 instance before the first deployment so Caddy can request the TLS certificate. Then push to `main` or run the `Deploy to EC2` workflow manually from GitHub Actions.

The workflow writes `/opt/rag-console/docker-compose.ec2.yml`, writes `.env`, installs and configures Nginx, requests a Let's Encrypt certificate for `rag.atharvaai.com`, pulls the new images, starts Postgres, Redis, API, worker, and web services, then checks health through both the API container and Nginx.

Nginx terminates HTTPS for `rag.atharvaai.com`, sends `/api/*`, `/docs`, `/redoc`, `/openapi.json`, and `/healthz` to the FastAPI service on `127.0.0.1:8000`, and sends all other traffic to the Next.js web service on `127.0.0.1:3000`.

If you move behind an ALB or another reverse proxy later, update `NEXT_PUBLIC_API_URL`, `APP_DOMAIN`, `WEB_BASE_URL`, and `CORS_ORIGINS` together.
