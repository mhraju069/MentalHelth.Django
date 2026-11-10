import email
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from . import email_branding
from .helper import send_otp

BACKBLAZE_STORAGES = {
    'default': {'BACKEND': 'core.storage_backends.PublicMediaStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class EmailLogoTests(TestCase):
    def setUp(self):
        email_branding._logo_bytes = None

    def tearDown(self):
        email_branding._logo_bytes = None

    @override_settings(PUBLIC_BASE_URL='https://api.thehoneysucklecompany.com/')
    def test_emails_link_to_our_permanent_logo_url(self):
        self.assertEqual(email_branding.email_logo_url(), 'https://api.thehoneysucklecompany.com/api/auth/email-logo.png')

    def test_endpoint_serves_the_logo_publicly_and_cacheably(self):
        response = self.client.get('/api/auth/email-logo.png')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('max-age', response['Cache-Control'])
        self.assertEqual(response.content, email_branding.LOGO_SOURCE.read_bytes())

    @override_settings(STORAGES=BACKBLAZE_STORAGES)
    def test_logo_is_uploaded_to_backblaze_once_and_served_from_there(self):
        storage = MagicMock()
        storage.exists.return_value = False
        storage.open.return_value = ContentFile(b'PNG-from-b2')
        with patch('core.storage_backends.PublicMediaStorage', return_value=storage):
            first = self.client.get('/api/auth/email-logo.png')
            second = self.client.get('/api/auth/email-logo.png')

        storage.save.assert_called_once()
        self.assertEqual(storage.save.call_args.args[0], email_branding.LOGO_NAME)
        storage.open.assert_called_once()  # kept in memory after the first read
        self.assertEqual((first.content, second.content), (b'PNG-from-b2', b'PNG-from-b2'))

    @override_settings(STORAGES=BACKBLAZE_STORAGES)
    def test_backblaze_failure_serves_the_bundled_logo(self):
        storage = MagicMock()
        storage.exists.side_effect = ConnectionError('B2 down')
        with patch('core.storage_backends.PublicMediaStorage', return_value=storage):
            response = self.client.get('/api/auth/email-logo.png')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, email_branding.LOGO_SOURCE.read_bytes())
        self.assertIsNone(email_branding._logo_bytes)  # retried next time


class OtpEmailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='reader@example.com', password='pass12345')

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

    @override_settings(PUBLIC_BASE_URL='https://api.thehoneysucklecompany.com')
    def test_logo_is_linked_not_attached(self):
        message = self.send()

        self.assertIn('src="https://api.thehoneysucklecompany.com/api/auth/email-logo.png"', self.html_of(message))
        self.assertEqual(self.inline_images(message), [])
        self.assertEqual(message['Subject'], 'Your Honeysuckle Trail verification code')

    @override_settings(PUBLIC_BASE_URL='')
    def test_without_a_site_url_the_logo_is_attached_inline(self):
        message = self.send()

        self.assertIn('src="cid:logo"', self.html_of(message))
        self.assertEqual(len(self.inline_images(message)), 1)

    def test_email_shows_code_expiry_and_task_wording(self):
        message = self.send(task='reset')
        html = self.html_of(message)
        code = self.user.user_otp.latest('created_at').otp

        self.assertEqual(message['Subject'], 'Reset your Honeysuckle Trail password')
        self.assertIn('Reset your password', html)
        self.assertIn('expires in 3 minutes', html)
        self.assertIn(code, html)


class SocialSignInNameTests(TestCase):
    """Google puts the name in the Firebase token; Apple only once, via the app."""

    def sign_in(self, **claims):
        token = {'uid': 'uid-1', 'email': 'apple@example.com', **claims}
        with patch('accounts.views.firebase_auth.verify_id_token', return_value=token):
            return self.client.post('/api/auth/?token=abc')

    def test_new_account_gets_the_name_from_the_token(self):
        response = self.sign_in(name='Jane Appleseed')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.get(email='apple@example.com').name, 'Jane Appleseed')

    def test_missing_name_is_filled_in_on_a_later_sign_in(self):
        self.sign_in()  # Apple first sign-in where the name didn't arrive
        self.assertFalse(get_user_model().objects.get(email='apple@example.com').name)

        self.sign_in(name='Jane Appleseed')
        self.assertEqual(get_user_model().objects.get(email='apple@example.com').name, 'Jane Appleseed')

    def test_existing_name_is_never_overwritten(self):
        self.sign_in(name='Jane Appleseed')
        user = get_user_model().objects.get(email='apple@example.com')
        user.name = 'Jane (edited in app)'
        user.save()

        self.sign_in(name='Jane Appleseed')
        self.assertEqual(get_user_model().objects.get(email='apple@example.com').name, 'Jane (edited in app)')


class ProfileFlagsTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

    def test_has_password_is_false_for_social_accounts(self):
        email_user = get_user_model().objects.create_user(email='pw@example.com', password='pass12345')
        # As FirebaseLoginView creates them.
        social = get_user_model().objects.create_user(email='social@example.com', uid='firebase-uid-1')

        for user, expected in ((email_user, True), (social, False)):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/auth/user/').data['has_password'], expected)

    def test_profile_request_saves_the_phone_timezone(self):
        user = get_user_model().objects.create_user(email='tz@example.com', password='pass12345')
        self.client.force_authenticate(user)

        self.client.get('/api/auth/user/', HTTP_X_TIMEZONE='America/New_York')
        user.refresh_from_db()
        self.assertEqual(user.timezone, 'America/New_York')

        self.client.get('/api/auth/user/')  # no header: leave it alone
        user.refresh_from_db()
        self.assertEqual(user.timezone, 'America/New_York')

        # Clients can't set it directly.
        self.client.patch('/api/auth/user/', {'timezone': 'Asia/Tokyo'}, format='json')
        user.refresh_from_db()
        self.assertEqual(user.timezone, 'America/New_York')
