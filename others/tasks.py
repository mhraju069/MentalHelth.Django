import logging, random
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
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
    now = timezone.now()
    # If project is using UTC, and user provides local time, we should handle timezones.
    # Currently sending based on the time stored, assuming it aligns with server time.
    
    current_hour = now.hour
    current_minute = now.minute
    
    users = User.objects.filter(
        notify=True,
        checkin_time__hour=current_hour,
        checkin_time__minute=current_minute
    )
    
    if users.exists():
        logger.info(f"Sending {users.count()} reminders for {current_hour:02}:{current_minute:02}")
        for user in users:
            send_single_reminder.delay(str(user.id))

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
