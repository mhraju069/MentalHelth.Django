from django.core.management.base import BaseCommand

from accounts.email_branding import _uses_backblaze, email_logo_bytes, email_logo_url


class Command(BaseCommand):
    help = 'Upload the email logo to Backblaze (if not there yet) and print the URL emails use.'

    def handle(self, *args, **options):
        size = len(email_logo_bytes())
        source = 'Backblaze' if _uses_backblaze() else 'the bundled file (Backblaze not configured)'
        self.stdout.write(f'Logo loaded from {source}: {size} bytes.')
        url = email_logo_url()
        if url:
            self.stdout.write(self.style.SUCCESS(f'Emails link to: {url}'))
        else:
            self.stdout.write(self.style.WARNING('PUBLIC_BASE_URL is not set; emails attach the logo instead.'))
