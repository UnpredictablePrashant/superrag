# EC2 Deployment

This deployment path builds the API and web Docker images in GitHub Actions, pushes them to GitHub Container Registry, copies a production Compose file to an EC2 instance, and restarts the stack over SSH.

## EC2 prerequisites

- Docker Engine with the Docker Compose plugin installed.
- A DNS `A` record for `rag.atharvaai.com` pointing at the EC2 public IP `18.188.234.72`. Prefer an Elastic IP so the record stays stable.
- A security group that allows SSH from your IP and public web traffic on ports `80` and `443`.
- An application directory on the instance, defaulting to `/opt/rag-console`.
- An S3 bucket and email provider credentials for production uploads and OTP email.

## GitHub configuration

Add these repository secrets:

- `EC2_SSH_KEY`: private SSH key that can connect to the instance.
- `EC2_ENV_FILE_B64`: base64-encoded contents of the EC2 `.env` file.
- `GHCR_TOKEN`: GitHub token with `read:packages` for pulling private GHCR images from EC2. Public packages can omit this.

Add these repository variables:

- `EC2_HOST`: optional host override. Defaults to `18.188.234.72`.
- `EC2_USER`: optional SSH username override. Defaults to `ubuntu`.
- `NEXT_PUBLIC_API_URL`: browser-facing API URL. Defaults to `https://rag.atharvaai.com/api`.
- `EC2_APP_DIR`: optional app directory override. Defaults to `/opt/rag-console`.
- `EC2_PORT`: optional SSH port override. Defaults to `22`.

Create and review the production env file:

```powershell
Copy-Item deploy\ec2\ec2.env.example .env.ec2.production
notepad .env.ec2.production
```

After replacing the placeholder values, encode it for the GitHub secret:

```powershell
$envText = Get-Content -Raw .env.ec2.production
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($envText))
```

Save the result as `EC2_ENV_FILE_B64`.

Generate a Fernet key for `ENCRYPTION_KEY` with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Deploy

Point `rag.atharvaai.com` at the EC2 instance before the first deployment so Caddy can request the TLS certificate. Then push to `main` or run the `Deploy to EC2` workflow manually from GitHub Actions.

The workflow writes `/opt/rag-console/docker-compose.ec2.yml`, writes `.env` when `EC2_ENV_FILE_B64` is set, pulls the new images, starts Postgres, Redis, API, worker, and web services, then checks `http://localhost:8000/healthz` inside the API container.

The EC2 Compose stack includes Caddy. It terminates HTTPS for `rag.atharvaai.com`, sends `/api/*`, `/docs`, `/redoc`, `/openapi.json`, and `/healthz` to the FastAPI service, and sends all other traffic to the Next.js web service.

If you move behind an ALB or another reverse proxy later, update `NEXT_PUBLIC_API_URL`, `APP_DOMAIN`, `WEB_BASE_URL`, and `CORS_ORIGINS` together.
