
import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()
from corsheaders.defaults import default_headers
import firebase_admin
from firebase_admin import credentials
BASE_DIR = Path(__file__).resolve().parent.parent

cred_path = os.path.join(BASE_DIR, "firebase-key.json")
if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
else:
    print(f"Warning: Firebase certificate not found at {cred_path}")

CORS_ALLOW_CREDENTIALS = True
DEBUG = os.getenv('DEBUG', True)
SECRET_KEY = os.getenv("SECRET_KEY")
BASE_DIR = Path(__file__).resolve().parent.parent
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
DATA_UPLOAD_MAX_MEMORY_SIZE = 1048576
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
CORS_ALLOW_HEADERS = list(default_headers) + ['ngrok-skip-browser-warning',]
CORS_ALLOW_ORIGINS =  os.getenv('CORS_ALLOW_ORIGINS', 'localhost:8000,localhost:3000,https://hecticly-rural-kittie.ngrok-free.dev').split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'localhost:8000,localhost:3000,hecticly-rural-kittie.ngrok-free.dev').split(',')

INSTALLED_APPS = [
    'unfold',
    'channels',
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'rest_framework',
    'rest_framework_simplejwt',
    'accounts',
    'others',

]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = 'core.asgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    'default':{
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'

USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static",]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        'rest_framework.filters.OrderingFilter',
        ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.CursorPagination',
    'PAGE_SIZE': None,
    }


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30)
}


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL")


# Celery Settings
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'send-daily-reminders-every-minute': {
        'task': 'others.tasks.send_daily_reminders',
        'schedule': crontab(minute='*'),  # Run every minute to check for users
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'others': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

UNFOLD = {
    "SITE_TITLE": "Honey Suckle Trail Admin",
    "SITE_HEADER": "Honey Suckle Trail",
    "SITE_LOGO": "/static/logo.png",
    "SITE_ICON": "/static/logo.png",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "COLORS": {
        "accent": {
            "50": "244 247 243",
            "100": "233 241 230",
            "200": "203 221 198",
            "300": "165 196 158",
            "400": "125 168 116",
            "500": "88 129 87",   # Brand Green #588157
            "600": "70 102 69",
            "700": "54 79 53",
            "800": "39 56 38",
            "900": "26 37 25",
            "950": "13 18 13",
        },
        "primary": {
            "50": "255 243 238",
            "100": "255 231 221",
            "200": "255 203 183",
            "300": "255 170 138",
            "400": "255 132 87",
            "500": "255 126 70",  # Brand Orange #FF7E46
            "600": "217 93 46",
            "700": "173 70 32",
            "800": "130 50 21",
            "900": "89 32 12",
            "950": "46 14 5",
        },
    },
}

