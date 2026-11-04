from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone


class UserTimezoneMiddleware:
    """
    Activate the timezone the app sends in the X-Timezone header (an IANA
    name such as "America/New_York"), so "today", streaks and monthly
    analytics follow the user's own day instead of the server's (UTC).
    Requests without a valid header stay in UTC.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        name = request.headers.get('X-Timezone', '').strip()
        try:
            tz = ZoneInfo(name) if name else None
        except (ZoneInfoNotFoundError, ValueError):
            tz = None

        if tz is None:
            timezone.deactivate()
        else:
            timezone.activate(tz)
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
