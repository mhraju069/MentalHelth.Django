"""
The logo shown in emails. The file lives in the (private) Backblaze B2
bucket; emails link to our own permanent URL, which serves it from there.
Signed B2 links can't be used in emails: they expire (7 days at most) and
people open emails later.
"""
import logging

from django.conf import settings
from django.core.files import File

logger = logging.getLogger(__name__)

LOGO_SOURCE = settings.BASE_DIR / 'static' / 'email-logo.png'
# Versioned name: upload a new logo under a new name.
LOGO_NAME = 'branding/email-logo-v1.png'
LOGO_PATH = '/api/auth/email-logo.png'

_logo_bytes = None


def _uses_backblaze():
    return settings.STORAGES['default']['BACKEND'] == 'core.storage_backends.PublicMediaStorage'


def email_logo_url():
    """Permanent public URL of the email logo, or None if the site URL isn't configured."""
    base = (getattr(settings, 'PUBLIC_BASE_URL', '') or '').rstrip('/')
    return f'{base}{LOGO_PATH}' if base else None


def email_logo_bytes():
    """
    The logo image. Read from Backblaze once per process (uploading it the
    first time); the bundled file is used if Backblaze isn't configured or
    can't be reached.
    """
    global _logo_bytes
    if _logo_bytes:
        return _logo_bytes

    if _uses_backblaze():
        from core.storage_backends import PublicMediaStorage

        storage = PublicMediaStorage()
        try:
            if not storage.exists(LOGO_NAME):
                with open(LOGO_SOURCE, 'rb') as f:
                    storage.save(LOGO_NAME, File(f))
            with storage.open(LOGO_NAME, 'rb') as f:
                _logo_bytes = f.read()
            return _logo_bytes
        except Exception:
            # Not cached, so the next request tries Backblaze again.
            logger.exception('Could not load the email logo from Backblaze')

    with open(LOGO_SOURCE, 'rb') as f:
        return f.read()
