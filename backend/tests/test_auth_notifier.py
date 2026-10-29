from __future__ import annotations

import smtplib
from dataclasses import replace
from email import message_from_string
from email.header import decode_header, make_header
from email.utils import parseaddr
from unittest.mock import MagicMock

import pytest

from app.core.auth_config import AuthSettings
from app.core.auth_email_template import render_verification_email
from app.core.auth_notifier import AuthNotifier


@pytest.fixture
def email_settings(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("AUTH_SECRET_KEY", "unit-test-secret-never-used-in-production")
    return replace(
        AuthSettings.from_env(), is_prod=False, smtp_host="", smtp_user="", smtp_pass="",
        smtp_from="", database_enabled=False, database_dsn="",
    )


@pytest.fixture(autouse=True)
def block_real_smtp(monkeypatch):
    plain = MagicMock(side_effect=AssertionError("A test attempted a real SMTP connection"))
    secure = MagicMock(side_effect=AssertionError("A test attempted a real SMTP SSL connection"))
    monkeypatch.setattr(smtplib, "SMTP", plain)
    monkeypatch.setattr(smtplib, "SMTP_SSL", secure)
    return plain, secure


@pytest.mark.parametrize("method", ["send_registration_code", "send_forgot_code"])
@pytest.mark.parametrize("contact", ["13900000000", "not-an-email", "name@@example.com", "name@example.com\r\nBcc: other@example.com"])
def test_notifier_rejects_non_email_without_contacting_smtp(email_settings, block_real_smtp, method, contact):
    result = getattr(AuthNotifier(email_settings), method)(contact, "123456")

    assert not result.ok
    assert "email" in result.error.lower()
    assert not result.dev_code
    for factory in block_real_smtp:
        factory.assert_not_called()


@pytest.mark.parametrize("method", ["send_registration_code", "send_forgot_code"])
def test_unconfigured_development_email_returns_explicit_simulation(email_settings, block_real_smtp, method):
    result = getattr(AuthNotifier(email_settings), method)("receiver@example.com", "123456")

    assert result.ok and result.dev_code == "123456"
    for factory in block_real_smtp:
        factory.assert_not_called()


@pytest.mark.parametrize("method", ["send_registration_code", "send_forgot_code"])
def test_unconfigured_production_email_fails_without_simulation(email_settings, block_real_smtp, method):
    result = getattr(AuthNotifier(replace(email_settings, is_prod=True)), method)("receiver@example.com", "123456")

    assert not result.ok and not result.dev_code
    for factory in block_real_smtp:
        factory.assert_not_called()


@pytest.mark.parametrize("method", ["send_registration_code", "send_forgot_code"])
@pytest.mark.parametrize("secure,port", [(False, 587), (True, 465)])
def test_smtp_delivers_to_the_email_recipient_only(email_settings, monkeypatch, block_real_smtp, method, secure, port):
    settings = replace(
        email_settings, smtp_host="smtp.example.com", smtp_port=port, smtp_secure=secure,
        smtp_user="sender@example.com", smtp_pass="smtp-test-password",
    )
    server = MagicMock()
    factory = MagicMock()
    factory.return_value.__enter__.return_value = server
    monkeypatch.setattr(smtplib, "SMTP_SSL" if secure else "SMTP", factory)

    result = getattr(AuthNotifier(settings), method)(" receiver@example.com ", "123456")

    assert result.ok and not result.dev_code
    factory.assert_called_once_with("smtp.example.com", port, timeout=20)
    server.login.assert_called_once_with("sender@example.com", "smtp-test-password")
    server.sendmail.assert_called_once()
    sender, recipients, raw = server.sendmail.call_args.args
    assert sender == "sender@example.com"
    assert recipients == ["receiver@example.com"]
    message = message_from_string(raw)
    assert message["To"] == "receiver@example.com"
    assert message.get_content_type() == "multipart/alternative"
    parts = message.get_payload()
    assert [part.get_content_type() for part in parts] == ["text/plain", "text/html"]
    for part in parts:
        assert part.get_content_charset() == "utf-8"
        text = part.get_payload(decode=True).decode("utf-8")
        assert "123456" in text and "文枢智动" in text
        assert "5 分钟" in text
    subject = str(make_header(decode_header(message["Subject"])))
    assert subject == ("【文枢智动】注册邮箱验证码" if method == "send_registration_code" else "【文枢智动】重置密码验证码")
    assert "123456" not in subject
    assert str(make_header(decode_header(parseaddr(message["From"])[0]))) == "文枢智动账号服务"
    if secure:
        server.starttls.assert_not_called()
        block_real_smtp[0].assert_not_called()
    else:
        server.starttls.assert_called_once()
        block_real_smtp[1].assert_not_called()


def test_smtp_failure_is_not_replaced_with_a_simulated_success(email_settings, monkeypatch):
    settings = replace(email_settings, smtp_host="smtp.example.com", smtp_user="sender@example.com", smtp_pass="test-password")
    server = MagicMock()
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    factory = MagicMock()
    factory.return_value.__enter__.return_value = server
    monkeypatch.setattr(smtplib, "SMTP", factory)

    result = AuthNotifier(settings).send_registration_code("receiver@example.com", "123456")

    assert not result.ok and not result.dev_code
    server.sendmail.assert_not_called()


@pytest.mark.parametrize("flow", ["register", "forgot"])
@pytest.mark.parametrize("expires_ms,expected", [(300000, "5 分钟"), (600000, "10 分钟"), (90000, "1 分钟 30 秒")])
def test_email_expiry_matches_config_and_flow(flow, expires_ms, expected):
    email = render_verification_email(flow=flow, code="012345", expires_ms=expires_ms)

    for body in (email.text, email.html):
        assert expected + "后失效" in body
        assert "012345" in body
        assert "文枢智动" in body
    assert "012345" not in email.subject
    if flow == "register":
        assert "全域知识图谱" in email.html
        assert "密码重置请求" not in email.text
    else:
        assert "密码重置请求" in email.text
        assert "如果不是你本人发起" in email.html
        assert "创建文枢智动账号" not in email.text


def test_email_html_escapes_dynamic_content():
    email = render_verification_email(flow="register", code='<script>alert("x")</script>', expires_ms=300000)
    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html


def test_email_template_rejects_unknown_flow():
    with pytest.raises(ValueError):
        render_verification_email(flow="unsupported", code="123456", expires_ms=300000)


def test_sender_preserves_explicit_address_and_display_name(email_settings):
    header, address = AuthNotifier(email_settings)._resolve_sender_identity(
        "自定义发件名称 <custom@example.com>", fallback_email="sender@example.com",
    )
    assert address == "custom@example.com"
    assert str(make_header(decode_header(parseaddr(header)[0]))) == "自定义发件名称"
