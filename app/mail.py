import os
import smtplib
from email.message import EmailMessage

def send_mail(to_addr: str, subject: str, content: str) -> bool:
    host = os.getenv('SMTP_HOST', '')
    sender = os.getenv('SMTP_FROM', '')
    if not host or not sender:
        print(f'[DEV MAIL] Destino: {to_addr}\nAssunto: {subject}\n{content}', flush=True)
        return False
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.set_content(content)
    port = int(os.getenv('SMTP_PORT', '587'))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if os.getenv('SMTP_USE_TLS', 'true').lower() == 'true':
            smtp.starttls()
        if os.getenv('SMTP_USER'):
            smtp.login(os.getenv('SMTP_USER', ''), os.getenv('SMTP_PASSWORD', ''))
        smtp.send_message(msg)
    return True
