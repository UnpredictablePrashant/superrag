from __future__ import annotations

import smtplib
from email.message import EmailMessage

import boto3

from app.core.config import settings
from app.core.logging import logger


def send_email(to_email: str, subject: str, text_body: str) -> None:
    if settings.email_backend == "console":
        logger.info("email.console", to=to_email, subject=subject)
        return

    if settings.email_backend == "ses":
        ses = boto3.client("ses", region_name=settings.aws_region)
        ses.send_email(
            Source=settings.email_from,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": text_body}},
            },
        )
        return

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(message)


def send_otp_email(email: str, code: str) -> None:
    send_email(
        email,
        "Your RAG Console sign-in code",
        f"Your RAG Console one-time code is {code}. It expires in {settings.otp_ttl_minutes} minutes.",
    )


def send_invitation_email(email: str, organization_name: str, invite_url: str) -> None:
    send_email(
        email,
        f"Join {organization_name} on RAG Console",
        f"You have been invited to {organization_name} on RAG Console.\n\nAccept: {invite_url}",
    )
