from django.core.management.base import BaseCommand

from accounts.email_branding import email_logo_url


class Command(BaseCommand):
    help = 'Upload the email logo to Backblaze (if not there yet) and print its public URL.'

    def handle(self, *args, **options):
        url = email_logo_url()
        if url:
            self.stdout.write(self.style.SUCCESS(f'Email logo: {url}'))
        else:
            self.stdout.write(self.style.WARNING(
                'Backblaze is not configured or not reachable; emails will attach the logo instead.'
            ))
