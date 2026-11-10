from django.utils import timezone
from datetime import timedelta
from .email_branding import LOGO_SOURCE, email_logo_url
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

OTP_EXPIRES_MINUTES = 3  # matches OTP.is_expired


def _otp_copy(task):
    """(subject, heading, intro) for the kind of code being sent."""
    if 'reset' in (task or '').lower() or 'forgot' in (task or '').lower():
        return (
            'Reset your Honeysuckle Trail password',
            'Reset your password',
            'Use this code to reset your password.',
        )
    return (
        'Your Honeysuckle Trail verification code',
        'Verify your email',
        'Use this code to finish signing in to Honeysuckle Trail.',
    )


def send_otp(email, task="verification"):
    try:
        user = User.objects.get(email=email)
        otp_obj = OTP.generate_otp(user)

        subject, heading, intro = _otp_copy(task)
        email_from = settings.EMAIL_HOST_USER
        plain_text = (
            f"{heading}\n\n{intro}\n\nYour code: {otp_obj.otp}\n"
            f"It expires in {OTP_EXPIRES_MINUTES} minutes.\n\n"
            "If you didn't request this, you can ignore this email."
        )
        # Logo served from our API (the file lives in Backblaze); falls back
        # to an inline attachment when the site URL isn't configured.
        logo_url = email_logo_url()
        html_content = render_to_string('email.html', {
            'otp': otp_obj.otp,
            'heading': heading,
            'intro': intro,
            'expires_minutes': OTP_EXPIRES_MINUTES,
            'logo_src': logo_url or 'cid:logo',
        })

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

        # No hosted logo: attach it inline so the template's cid:logo resolves.
        if not logo_url and os.path.exists(LOGO_SOURCE):
            with open(LOGO_SOURCE, 'rb') as f:
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

