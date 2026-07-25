from email.message import EmailMessage

from aiosmtplib import send

from config.settings import SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER


async def send_email(email: str, code: str) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be configured")

    message = EmailMessage()
    message["From"] = SMTP_USER
    message["To"] = email
    message["Subject"] = "验证码"
    message.set_content(f"您的验证码是：{code}\n验证码有效期为 5 分钟。")

    try:
        await send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=SMTP_PORT == 465,
        )

        print(
            f"邮件发送成功:{email}"
        )

    except Exception as e:

        print(
            f"邮件发送失败:{email}, 原因:{e}"
        )

        raise