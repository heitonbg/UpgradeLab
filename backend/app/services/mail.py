import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote
from app.core.config import settings


def configured():
    return bool(settings.smtp_host and settings.smtp_from and
                settings.smtp_security in ("starttls", "ssl", "none"))


def send_reset_email(address, token):
    message = EmailMessage()
    message["Subject"] = "UpgradeLab — восстановление пароля"
    message["From"] = settings.smtp_from
    message["To"] = address
    link = settings.frontend_url.rstrip("/") + "/#reset_token=" + quote(token)
    message.set_content("Чтобы задать новый пароль UpgradeLab, откройте ссылку:\n\n" + link +
                        "\n\nСсылка действует 30 минут и используется один раз. "
                        "Если вы не запрашивали восстановление, проигнорируйте письмо.")
    context = ssl.create_default_context()
    connection = (smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context)
                  if settings.smtp_security == "ssl" else smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15))
    with connection as client:
        if settings.smtp_security == "starttls":
            client.starttls(context=context)
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
