"""Transactional email helpers backed by Brevo's HTTP API."""

import asyncio
from html import escape

from src.security.outbound_http import OutboundResponseError, UnsafeOutboundUrl, post_json, validate_outbound_url

from config.loader import (
    BREVO_API_KEY,
    BREVO_FROM_EMAIL,
    BREVO_FROM_NAME,
    BREVO_REQUEST_TIMEOUT_SECONDS,
    PUBLIC_APP_URL,
    OPERATING_MODE,
)

BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be handed to Brevo."""


def public_url(path: str) -> str:
    """Return an absolute application URL for a path included in an email."""
    value = f"{PUBLIC_APP_URL}/{path.lstrip('/')}"
    validate_outbound_url(value, allow_http=OPERATING_MODE == "development", resolve=False)
    return value


def _action_email_html(
    *,
    heading: str,
    greeting_name: str,
    body: str,
    action_label: str,
    action_url: str,
    expiry_text: str,
) -> str:
    safe_brand = escape(BREVO_FROM_NAME)
    safe_heading = escape(heading)
    safe_name = escape(greeting_name or "usuario")
    safe_body = escape(body)
    safe_label = escape(action_label)
    safe_url = escape(action_url, quote=True)
    safe_expiry = escape(expiry_text)
    return f"""<!doctype html>
<html lang="es">
  <body style="margin:0;background:#191917;color:#f5f4ef;font-family:Arial,sans-serif">
    <div style="max-width:560px;margin:0 auto;padding:32px 20px">
      <div style="border-top:4px solid #f05a28;background:#282825;padding:28px">
        <p style="margin:0 0 8px;color:#f05a28;font-weight:700;letter-spacing:.08em;text-transform:uppercase">{safe_brand}</p>
        <h1 style="margin:0 0 20px;font-size:28px">{safe_heading}</h1>
        <p>Hola {safe_name},</p>
        <p style="line-height:1.6;color:#d7d5ce">{safe_body}</p>
        <p style="margin:28px 0">
          <a href="{safe_url}" style="display:inline-block;background:#f05a28;color:#fff;text-decoration:none;font-weight:700;padding:13px 20px;border-radius:8px">{safe_label}</a>
        </p>
        <p style="line-height:1.5;color:#aaa89f;font-size:13px">{safe_expiry}</p>
        <p style="line-height:1.5;color:#aaa89f;font-size:13px">Si el botón no funciona, copia este enlace en tu navegador:<br><a href="{safe_url}" style="color:#f58a64;overflow-wrap:anywhere">{safe_url}</a></p>
        <p style="margin-top:24px;line-height:1.5;color:#aaa89f;font-size:13px">Si no solicitaste este correo, puedes ignorarlo.</p>
      </div>
    </div>
  </body>
</html>"""


async def send_email(
    *,
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None = None,
    to_name: str = "",
    attachments: list[dict[str, str]] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Send one transactional email and return Brevo's message id."""
    if not BREVO_API_KEY or not BREVO_FROM_EMAIL:
        raise EmailDeliveryError("Brevo email credentials are not configured.")

    payload: dict[str, object] = {
        "sender": {"email": BREVO_FROM_EMAIL, "name": BREVO_FROM_NAME},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html_content,
    }
    if text_content is not None:
        payload["textContent"] = text_content
    if attachments:
        payload["attachment"] = attachments
    if tags:
        payload["tags"] = tags

    try:
        status, response_body = await asyncio.to_thread(
            post_json,
            BREVO_TRANSACTIONAL_EMAIL_URL,
            headers={"Accept": "application/json", "api-key": BREVO_API_KEY},
            json_payload=payload,
            connect_timeout=BREVO_REQUEST_TIMEOUT_SECONDS,
            read_timeout=BREVO_REQUEST_TIMEOUT_SECONDS,
        )
    except (OutboundResponseError, UnsafeOutboundUrl, ValueError) as exc:
        # Never include provider response bodies, email contents or API keys in errors.
        raise EmailDeliveryError("Brevo delivery failed (transport or response validation).") from exc
    if not 200 <= status < 300:
        raise EmailDeliveryError(f"Brevo delivery failed (HTTP {status}).")

    if not isinstance(response_body, dict):
        raise EmailDeliveryError("Brevo returned an invalid delivery response.")
    message_id = response_body.get("messageId")
    if not isinstance(message_id, str) or not message_id:
        raise EmailDeliveryError("Brevo returned an invalid delivery response.")
    return message_id


async def _send_access_email(
    *,
    to_email: str,
    to_name: str,
    subject: str,
    heading: str,
    body: str,
    action_label: str,
    access_path: str,
    expiry_text: str,
    tag: str,
) -> str:
    access_url = public_url(access_path)
    return await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        html_content=_action_email_html(
            heading=heading,
            greeting_name=to_name,
            body=body,
            action_label=action_label,
            action_url=access_url,
            expiry_text=expiry_text,
        ),
        tags=[tag],
    )


async def send_verification_email(*, to_email: str, to_name: str, onboarding_path: str) -> str:
    """Email a new user their one-time account activation link."""
    return await _send_access_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"Activa tu cuenta de {BREVO_FROM_NAME}",
        heading="Activa tu cuenta",
        body="Confirma tu correo y crea tu contraseña para comenzar a usar tu cuenta.",
        action_label="Activar mi cuenta",
        access_path=onboarding_path,
        expiry_text="Este acceso vence en 24 horas y solo puede utilizarse una vez.",
        tag="account-verification",
    )


async def send_password_reset_email(*, to_email: str, to_name: str, reset_path: str) -> str:
    """Email a user their one-time password reset link."""
    return await _send_access_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"Restablece tu contraseña de {BREVO_FROM_NAME}",
        heading="Restablece tu contraseña",
        body="Recibimos una solicitud para crear una nueva contraseña para tu cuenta.",
        action_label="Crear nueva contraseña",
        access_path=reset_path,
        expiry_text="Este acceso vence en 1 hora y solo puede utilizarse una vez.",
        tag="password-reset",
    )
