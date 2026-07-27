from email.message import EmailMessage
from email.utils import formataddr

from aiosmtplib import send

from config.settings import SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER


async def send_email(email: str, code: str) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be configured")

    message = EmailMessage()
    message["From"] = formataddr(("OpenCap", SMTP_USER))
    message["To"] = email
    message["Reply-To"] = SMTP_USER
    message["Subject"] = "OpenCap verification code"
    message.set_content(
        f"Your OpenCap verification code is: {code}\n"
        "This code is valid for 5 minutes.\n"
    )

    try:
        send_errors, response = await send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=SMTP_PORT == 465,
        )
        if send_errors:
            raise RuntimeError(f"SMTP refused recipients: {send_errors}")

        print(f"Email submitted successfully: {email}, response: {response}")

    except Exception as exc:
        print(f"Email send failed: {email}, reason: {exc}")
        raise
