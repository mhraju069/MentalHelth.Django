from django.utils import timezone
from datetime import timedelta
from .models import OTP, User
from django.core.mail import send_mail, EmailMultiAlternatives
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

def send_otp(email, task="verification"):
    try:
        user = User.objects.get(email=email)
        otp_obj = OTP.generate_otp(user)
        
        subject = f"Your OTP code for Mental Health Journal"
        email_from = settings.EMAIL_HOST_USER
        recipient_list = [email]
        
        # Render HTML template
        html_content = render_to_string('email.html', {'otp': otp_obj.otp, 'task': task})
        plain_text = f"Your OTP code is {otp_obj.otp}. It will expire in 3 minutes."
        
        msg = EmailMultiAlternatives(subject, plain_text, email_from, recipient_list)
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
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

