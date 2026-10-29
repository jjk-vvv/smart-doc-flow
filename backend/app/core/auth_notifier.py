from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from app.core.auth_config import AuthSettings
from app.core.auth_email_template import SENDER_NAME, render_verification_email
from app.core.auth_security import is_email, normalize_str

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    error: str = ""
    dev_code: str = ""


class AuthNotifier:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings

    def send_registration_code(self, contact: str, code: str) -> DeliveryResult:
        return self._send_email_code(contact, code, flow="register")

    def send_forgot_code(self, contact: str, code: str) -> DeliveryResult:
        return self._send_email_code(contact, code, flow="forgot")

    def _send_email_code(self, contact: str, code: str, *, flow: str) -> DeliveryResult:
        contact = normalize_str(contact)
        if not is_email(contact):
            return DeliveryResult(ok=False, error="Please enter a valid email address.")

        host = normalize_str(self.settings.smtp_host)
        user = normalize_str(self.settings.smtp_user)
        password = normalize_str(self.settings.smtp_pass)
        sender_header, sender_address = self._resolve_sender_identity(
            normalize_str(self.settings.smtp_from),
            fallback_email=user,
        )

        if not host or not user or not password or not sender_address:
            if not self.settings.is_prod:
                logger.info("[DEV][EMAIL] %s verification code: %s", contact, code)
                return DeliveryResult(ok=True, dev_code=code)
            return DeliveryResult(ok=False, error="Email service is not configured.")

        content = render_verification_email(flow=flow, code=code, expires_ms=self.settings.verify_code_expires_ms)

        try:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(content.text, "plain", "utf-8"))
            message.attach(MIMEText(content.html, "html", "utf-8"))
            message["Subject"] = content.subject
            message["From"] = sender_header
            message["To"] = contact

            if self.settings.smtp_secure:
                with smtplib.SMTP_SSL(host, self.settings.smtp_port, timeout=20) as server:
                    server.login(user, password)
                    server.sendmail(sender_address, [contact], message.as_string())
            else:
                with smtplib.SMTP(host, self.settings.smtp_port, timeout=20) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(user, password)
                    server.sendmail(sender_address, [contact], message.as_string())
        except Exception as exc:
            logger.exception("Email send failed: %s", exc)
            return DeliveryResult(ok=False, error="Email send failed. Please retry later.")

        return DeliveryResult(ok=True)

    def _resolve_sender_identity(self, sender: str, *, fallback_email: str) -> tuple[str, str]:
        raw_sender = normalize_str(sender) or normalize_str(fallback_email)
        display_name, email_address = parseaddr(raw_sender)
        email_address = normalize_str(email_address) or normalize_str(fallback_email)
        display_name = normalize_str(display_name).strip("\"'")

        if not email_address:
            return "", ""
        if not display_name:
            display_name = SENDER_NAME
        return formataddr((str(Header(display_name, "utf-8")), email_address)), email_address
