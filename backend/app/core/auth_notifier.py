from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

import requests

from app.core.auth_config import AuthSettings
from app.core.auth_security import normalize_str

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
        if "@" in contact:
            return self._send_email_code(contact, code, flow="register")
        return self._send_sms_code(contact, code)

    def send_forgot_code(self, contact: str, code: str) -> DeliveryResult:
        if "@" in contact:
            return self._send_email_code(contact, code, flow="forgot")
        return self._send_sms_code(contact, code)

    def _send_sms_code(self, contact: str, code: str) -> DeliveryResult:
        if self.settings.sms_provider != "ihuyi":
            if not self.settings.is_prod:
                logger.info("[DEV][SMS] %s verification code: %s", contact, code)
                return DeliveryResult(ok=True)
            return DeliveryResult(ok=False, error="SMS service is not configured.")

        api_id = normalize_str(self.settings.ihuyi_api_id)
        api_key = normalize_str(self.settings.ihuyi_api_key)
        if not api_id or not api_key:
            return DeliveryResult(ok=False, error="SMS credentials are incomplete.")

        try:
            response = requests.post(
                "https://106.ihuyi.com/webservice/sms.php?method=Submit",
                data={
                    "method": "Submit",
                    "account": api_id,
                    "password": api_key,
                    "mobile": contact,
                    "content": f"Your verification code is {code}. Please do not share it with others.",
                    "format": "json",
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.exception("SMS API call failed: %s", exc)
            return DeliveryResult(
                ok=False,
                error="SMS service is temporarily unavailable. Please retry later.",
            )

        if int(payload.get("code") or 0) == 2:
            if not self.settings.is_prod:
                logger.info("[IHUYI SMS Sent] %s verification code: %s", contact, code)
            return DeliveryResult(ok=True, dev_code="" if self.settings.is_prod else code)

        return DeliveryResult(
            ok=False,
            error=f"SMS send failed: {normalize_str(payload.get('msg')) or 'Please retry later'}",
        )

    def _send_email_code(self, contact: str, code: str, *, flow: str) -> DeliveryResult:
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

        subject = (
            "[Platform] Registration verification code"
            if flow == "register"
            else "[Platform] Password reset verification code"
        )
        title = "Registration Code" if flow == "register" else "Password Reset Code"
        context = (
            "You are registering an account. Your verification code is:"
            if flow == "register"
            else "You are resetting your password. Your verification code is:"
        )

        html = f"""
        <div style="max-width:480px;margin:0 auto;padding:32px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
          <h2 style="color:#1e293b;margin-bottom:8px;">{title}</h2>
          <p style="color:#64748b;font-size:14px;">{context}</p>
          <div style="background:#f1f5f9;border-radius:12px;padding:20px;text-align:center;margin:24px 0;">
            <span style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#2563eb;">{code}</span>
          </div>
          <p style="color:#64748b;font-size:13px;">The code is valid for 5 minutes. Please do not share it.</p>
        </div>
        """.strip()

        try:
            message = MIMEText(html, "html", "utf-8")
            message["Subject"] = subject
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
            return email_address, email_address
        return formataddr((str(Header(display_name, "utf-8")), email_address)), email_address
