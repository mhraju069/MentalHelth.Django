import logging
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from .utils import send_fcm_notification

User = get_user_model()
logger = logging.getLogger(__name__)

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
            send_fcm_notification(
                user, 
                "Daily Check-in Prompt", 
                "Hi there! Time to log your mental well-being for today."
            )
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found.")
