import logging
from firebase_admin import messaging
from .models import FCMDevice, Notification, DailyReport
from django.utils import timezone


logger = logging.getLogger(__name__)

def send_fcm_notification(user, title, body, data=None):
    """
    Sends a push notification to all active devices of a user.
    """
    devices = FCMDevice.objects.filter(user=user, active=True)
    logger.info(f"Attempting to send FCM to user {user.email}. Found {devices.count()} active devices.")
    if not devices.exists():
        logger.info(f"No active FCM devices found for user {user.email}")
        # Even if no devices, we might want to save the notification for the user to see later in-app
    
    # Save notification to DB
    Notification.objects.create(
        user=user,
        title=title,
        body=body,
        data=data or {}
    )

    if not devices.exists():
        return False

    tokens = list(devices.values_list('registration_id', flat=True))
    
    try:
        # Check if initialized
        import firebase_admin
        try:
            firebase_admin.get_app()
        except ValueError:
            logger.error("Firebase Admin SDK not initialized!")
            return False
            
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=tokens,
        )

        response = messaging.send_each_for_multicast(message)
        logger.info(f"Successfully sent {response.success_count} messages to user {user.email}")
        
        # Handle failed tokens (optional: deactivate them)
        if response.failure_count > 0:
            for i, resp in enumerate(response.responses):
                if not resp.success:
                    # Deactivate invalid tokens automatically
                    FCMDevice.objects.filter(registration_id=tokens[i]).update(active=False)
                    logger.warning(f"Deactivated invalid token {tokens[i][:20]}...: {resp.exception}")
                    
        return response.success_count > 0
    except Exception as e:
        logger.exception(f"Error sending FCM notification: {e}")
        return False


def calculate_streak(user):
    """
    Calculates the current check-in streak for a user.
    """
    reports = DailyReport.objects.filter(user=user)
    report_dates = reports.dates('time', 'day', order='DESC')
    
    streak = 0
    today = timezone.now().date()
    previous_date = None
    
    for report_date in report_dates:
        if previous_date is None:
            # The streak must start either today or yesterday to be active
            if (today - report_date).days <= 1:
                streak += 1
                previous_date = report_date
            else:
                # Streak is broken
                if (today - report_date).days > 1:
                    break
        else:
            # Check for consecutive days backwards
            if (previous_date - report_date).days == 1:
                streak += 1
                previous_date = report_date
            else:
                # Gap found, streak ends
                break
                
    return streak