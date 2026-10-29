from __future__ import annotations

from dataclasses import dataclass
from html import escape


SENDER_NAME = "文枢智动账号服务"


@dataclass(frozen=True)
class VerificationEmail:
    subject: str
    text: str
    html: str


def render_verification_email(*, flow: str, code: str, expires_ms: int) -> VerificationEmail:
    if flow not in {"register", "forgot"}:
        raise ValueError(f"Unsupported verification email flow: {flow}")

    minutes, seconds = divmod(max(1, (expires_ms + 999) // 1000), 60)
    duration = (f"{minutes} 分钟" if minutes else "") + (f" {seconds} 秒" if seconds else "")
    duration = duration.strip()
    if flow == "register":
        subject = "【文枢智动】注册邮箱验证码"
        title = "欢迎使用文枢智动"
        context = "你正在创建文枢智动账号。请返回注册页面，输入以下验证码，完成邮箱验证："
        purpose = "本次注册"
        notice = "如果你没有申请注册，请忽略此邮件。"
        footer = "智能文档解析 · 自定义智能填表 · 全域知识图谱"
        preview = "验证你的注册邮箱，继续创建文枢智动账号。"
    else:
        subject = "【文枢智动】重置密码验证码"
        title = "验证邮箱，重设密码"
        context = "我们收到了一次针对你账号的密码重置请求。请返回密码重置页面，输入以下验证码："
        purpose = "本次密码重置"
        notice = "如果不是你本人发起，请忽略此邮件，并勿向他人提供验证码。"
        footer = "文枢智动 · 账号服务"
        preview = "用邮箱验证码继续重置密码；如非本人操作，请忽略此邮件。"

    expiry = f"验证码将在 {duration}后失效，仅用于{purpose}。"
    text = "\n\n".join((
        "文枢智动 · Smart Doc Flow", title, context, code, expiry,
        "请勿向他人透露验证码。", notice, footer,
        "此邮件由文枢智动账号服务自动发送。",
    ))
    html = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{subject}</title></head>
<body style="margin:0;padding:0;background-color:#f3f6fa;color:#243449;font-family:'Microsoft YaHei','PingFang SC',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">{preview}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f3f6fa">
<tr><td align="center" style="padding:32px 16px;">
  <!--[if mso]><table role="presentation" width="560" align="center"><tr><td><![endif]-->
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background-color:#ffffff;border:1px solid #dfe6ef;border-top:3px solid #2563eb;border-radius:8px;">
    <tr><td style="padding:28px 24px 24px;border-bottom:1px solid #edf1f6;">
      <p style="margin:0;color:#1e3553;font-size:20px;font-weight:700;line-height:30px;">文枢智动</p>
      <p style="margin:4px 0 0;color:#738298;font-size:12px;line-height:20px;letter-spacing:1px;">SMART DOC FLOW · 账号服务</p>
    </td></tr>
    <tr><td style="padding:30px 24px 28px;">
      <h1 style="margin:0 0 18px;color:#1e293b;font-size:24px;font-weight:600;line-height:36px;">{title}</h1>
      <p style="margin:0 0 24px;color:#536278;font-size:15px;line-height:27px;">{context}</p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f0f5fc;border:1px solid #dce7f6;border-radius:6px;">
        <tr><td align="center" style="padding:20px 12px 22px;">
          <p style="margin:0 0 10px;color:#61748e;font-size:12px;line-height:20px;">{purpose}验证码</p>
          <p style="margin:0;color:#245bd7;font-family:Consolas,'Courier New',monospace;font-size:32px;font-weight:700;line-height:44px;letter-spacing:6px;white-space:nowrap;">{escape(code)}</p>
        </td></tr>
      </table>
      <p style="margin:18px 0 0;color:#536278;font-size:13px;line-height:24px;">{expiry}<br>请勿向他人透露验证码。</p>
      <p style="margin:22px 0 0;padding-top:20px;border-top:1px solid #edf1f6;color:#738298;font-size:13px;line-height:24px;">{notice}</p>
    </td></tr>
    <tr><td style="padding:18px 24px;background-color:#f8fafc;border-top:1px solid #edf1f6;">
      <p style="margin:0;color:#61748e;font-size:12px;line-height:22px;">{footer}</p>
      <p style="margin:4px 0 0;color:#8a97a8;font-size:11px;line-height:20px;">此邮件由文枢智动账号服务自动发送。</p>
    </td></tr>
  </table>
  <!--[if mso]></td></tr></table><![endif]-->
</td></tr></table>
</body></html>"""
    return VerificationEmail(subject=subject, text=text, html=html)
