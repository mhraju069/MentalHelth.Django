import email
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from . import email_branding
from .helper import send_otp

BACKBLAZE_STORAGES = {
    'default': {'BACKEND': 'core.storage_backends.PublicMediaStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
LOGO_URL = 'https://f004.backblazeb2.com/file/bucket/media/branding/email-logo-v1.png'


class OtpEmailTests(TestCase):
    def setUp(self):
        email_branding._logo_url = None
        self.user = get_user_model().objects.create_user(email='reader@example.com', password='pass12345')

    def tearDown(self):
        email_branding._logo_url = None

    def send(self, task='verification'):
        """Send an OTP email with SMTP mocked; return the parsed message."""
        with patch('accounts.helper.smtplib.SMTP') as smtp:
            result = send_otp(self.user.email, task)
        self.assertTrue(result['status'], result)
        raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
        return email.message_from_string(raw)

    @staticmethod
    def html_of(message):
        return next(p for p in message.walk() if p.get_content_type() == 'text/html').get_payload(decode=True).decode()

    @staticmethod
    def inline_images(message):
        return [p for p in message.walk() if p.get_content_type().startswith('image/')]

    def test_without_backblaze_the_logo_is_attached_inline(self):
        message = self.send()

        self.assertIn('src="cid:logo"', self.html_of(message))
        self.assertEqual(len(self.inline_images(message)), 1)
        self.assertEqual(message['Subject'], 'Your Honeysuckle Trail verification code')

    @override_settings(STORAGES=BACKBLAZE_STORAGES)
    def test_with_backblaze_the_logo_is_uploaded_once_and_linked(self):
        storage = MagicMock()
        storage.exists.side_effect = [False, True]
        storage.url.return_value = LOGO_URL
        with patch('core.storage_backends.PublicMediaStorage', return_value=storage) as cls:
            first = self.send()
            second = self.send()

        # Unsigned URLs, since signed ones expire before people open the email.
        cls.assert_called_with(querystring_auth=False)
        storage.save.assert_called_once()
        self.assertEqual(storage.save.call_args.args[0], email_branding.LOGO_NAME)
        for message in (first, second):
            self.assertIn(f'src="{LOGO_URL}"', self.html_of(message))
            self.assertEqual(self.inline_images(message), [])

    @override_settings(STORAGES=BACKBLAZE_STORAGES)
    def test_backblaze_failure_falls_back_to_inline_logo(self):
        storage = MagicMock()
        storage.exists.side_effect = ConnectionError('B2 down')
        with patch('core.storage_backends.PublicMediaStorage', return_value=storage):
            message = self.send()

        self.assertIn('src="cid:logo"', self.html_of(message))
        self.assertEqual(len(self.inline_images(message)), 1)
        self.assertIsNone(email_branding._logo_url)  # retried on the next email

    def test_email_shows_code_expiry_and_task_wording(self):
        message = self.send(task='reset')
        html = self.html_of(message)
        code = self.user.user_otp.latest('created_at').otp

        self.assertEqual(message['Subject'], 'Reset your Honeysuckle Trail password')
        self.assertIn('Reset your password', html)
        self.assertIn('expires in 3 minutes', html)
        self.assertIn(code, html)
