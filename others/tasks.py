import logging, random
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import DailyReport
from .utils import send_fcm_notification

User = get_user_model()
logger = logging.getLogger(__name__)

REMINDER_MESSAGES = [
    "How are you feeling today? Take a moment to check in.",
    "Ready to log your mood? It only takes a minute!",
    "Time for your daily reflection. How has your day been so far?",
    "A quick check-in can make a big difference. How's your mind today?",
    "Checking in on you! How are things going?",
    "Let's take a pause. How are you feeling right now?",
    "Your daily mental health check-in is ready. How are you?",
]

@shared_task
def send_daily_reminders():
    """
    Periodic task that runs every minute to check if any user needs a reminder.
    Reminders are sent if notify is True and checkin_time (hour/minute) matches the current time.
    """
    for user_id in users_due_for_reminder(timezone.now()):
        send_single_reminder.delay(str(user_id))


def users_due_for_reminder(now):
    """
    Users whose reminder time is this minute in their own timezone and who
    haven't checked in yet today (their local day).
    """
    due = []
    users = User.objects.filter(notify=True, is_active=True).only('id', 'checkin_time', 'timezone')
    for user in users.iterator():
        try:
            tz = ZoneInfo(user.timezone or 'UTC')
        except (ZoneInfoNotFoundError, ValueError):
            tz = ZoneInfo('UTC')
        local_now = now.astimezone(tz)
        if (local_now.hour, local_now.minute) != (user.checkin_time.hour, user.checkin_time.minute):
            continue
        day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        if DailyReport.objects.filter(user_id=user.id, created_at__gte=day_start).exists():
            continue
        due.append(user.id)
    if due:
        logger.info(f"Sending {len(due)} check-in reminder(s)")
    return due

@shared_task
def send_single_reminder(user_id):
    """ Sends a notification to a specific user. """
    try:
        user = User.objects.get(id=user_id)
        if user.notify:
            message = random.choice(REMINDER_MESSAGES)
            send_fcm_notification(
                user, 
                "Daily Check-in Reminder", 
                message
            )
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found.")


@shared_task
def send_streak_notification(user_id, streak_days):
    """ Sends a streak achievement notification. """
    try:
        user = User.objects.get(id=user_id)
        
        if streak_days == 3:
            title = "3-Day Streak! ⚡"
            body = "You've checked in for 3 days in a row. Great start!"
        elif streak_days == 7:
            title = "Weekly Streak! 🔥"
            body = "You've successfully completed 7 days of check-ins. Keep it up!"
        else:
            # Fallback if other days are added
            title = f"{streak_days}-Day Streak!"
            body = f"You've successfully completed {streak_days} days of check-ins!"

        send_fcm_notification(user, title, body)
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found.")


@shared_task
def send_ai_insight_notification(user_id):
    """ Sends a notification when new AI insights are available. """
    try:
        user = User.objects.get(id=user_id)
        send_fcm_notification(
            user,
            "New AI Insight Available",
            "Your mood patterns from the last 7 days are ready to view."
        )
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found.")


@shared_task
def send_resource_recommendation_notification(user_id):
    """ Sends a resource recommendation notification. """
    try:
        user = User.objects.get(id=user_id)
        send_fcm_notification(
            user,
            "Resource Recommendation",
            "We found a new meditation exercise you might like."
        )
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found.")


@shared_task
def sync_openai_usage():
    """Hourly: pull OpenAI costs/usage for the admin dashboard and warn if credit is low."""
    from .openai_billing import sync_and_check
    sync_and_check()


@shared_task
def report_openai_out_of_credit():
    from .openai_billing import report_out_of_credit
    report_out_of_credit()
