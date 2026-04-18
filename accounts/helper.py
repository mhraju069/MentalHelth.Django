from django.utils import timezone
from datetime import timedelta
from .models import OTP, User
from django.template.loader import render_to_string
from django.conf import settings
from rest_framework.response import Response
import json
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
from django.contrib.auth.hashers import make_password
from django.utils.text import slugify
from django.core.files.base import ContentFile
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

def send_otp(email, task="verification"):
    try:
        user = User.objects.get(email=email)
        otp_obj = OTP.generate_otp(user)

        subject = "Your OTP code for Honey Suckle Trail"
        email_from = settings.EMAIL_HOST_USER
        plain_text = f"Your OTP code is {otp_obj.otp}. It will expire in 3 minutes."
        html_content = render_to_string('email.html', {'otp': otp_obj.otp, 'task': task})

        # Build multipart/related to support inline images
        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = subject
        msg_root['From'] = email_from
        msg_root['To'] = email

        # multipart/alternative holds the plain-text + html alternatives
        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)
        msg_alternative.attach(MIMEText(plain_text, 'plain'))
        msg_alternative.attach(MIMEText(html_content, 'html'))

        # Attach logo inline with CID so the template can reference it via cid:logo
        logo_path = os.path.join(settings.MEDIA_ROOT, 'logo.png')
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header('Content-ID', '<logo>')
                img.add_header('Content-Disposition', 'inline', filename='logo.png')
                msg_root.attach(img)

        # Send via Django's SMTP settings
        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
            server.ehlo()
            if settings.EMAIL_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.sendmail(email_from, [email], msg_root.as_string())

        return {"status": True, "log": f"OTP sent successfully to {email}"}
    except User.DoesNotExist:
        return {"status": False, "log": "User with this email does not exist."}
    except Exception as e:
        return {"status": False, "log": str(e)}


def verify_otp(email, otp_code):
    try:
        otp_obj = OTP.objects.filter(user__email=email).latest('created_at')
    except OTP.DoesNotExist:
        return {"status": False, "log": "Invalid OTP or email."}

    # Check expiry
    if otp_obj.is_expired():
        return {"status": False, "log": "OTP has expired."}

    # Verify OTP
    if otp_obj.otp != otp_code:
        return {"status": False, "log": "Invalid OTP."}

    # OTP verified, activate user & delete OTP
    user = otp_obj.user
    user.is_active = True
    user.save()
    otp_obj.delete()

    return {"status": True, "log": "OTP verified statusfully."}

