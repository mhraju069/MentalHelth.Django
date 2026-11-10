"""
The logo shown in emails, hosted in the configured Backblaze B2 bucket so
mail apps load it from a plain public URL (inline attachments are often
blocked or shown as files).
"""
import logging

from django.conf import settings
from django.core.files import File

logger = logging.getLogger(__name__)

LOGO_SOURCE = settings.BASE_DIR / 'static' / 'email-logo.png'
# Versioned name: upload a new logo under a new name so cached copies in
# old emails and mail-provider image proxies don't go stale.
LOGO_NAME = 'branding/email-logo-v1.png'

_logo_url = None


def _uses_backblaze():
    return settings.STORAGES['default']['BACKEND'] == 'core.storage_backends.PublicMediaStorage'


def email_logo_url():
    """
    Public URL of the email logo in Backblaze, uploading it the first time.
    None when Backblaze isn't configured or isn't reachable; callers then
    attach the logo to the email instead.
    """
    global _logo_url
    if _logo_url or not _uses_backblaze():
        return _logo_url

    from core.storage_backends import PublicMediaStorage

    # Unsigned URL: signed ones expire, and emails are opened days later.
    storage = PublicMediaStorage(querystring_auth=False)
    try:
        if not storage.exists(LOGO_NAME):
            with open(LOGO_SOURCE, 'rb') as f:
                storage.save(LOGO_NAME, File(f))
        _logo_url = storage.url(LOGO_NAME)
    except Exception:
        # Not cached, so the next email tries again.
        logger.exception('Could not upload the email logo to Backblaze')
    return _logo_url
