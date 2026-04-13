import logging
from firebase_admin import messaging
from .models import FCMDevice, Notification


logger = logging.getLogger(__name__)

def send_fcm_notification(user, title, body, data=None):
    """
    Sends a push notification to all active devices of a user.
    """
    devices = FCMDevice.objects.filter(user=user, active=True)
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
    
    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        tokens=tokens,
    )

    try:
        response = messaging.send_multicast(message)
        logger.info(f"Successfully sent {response.success_count} messages to user {user.email}")
        
        # Handle failed tokens (optional: deactivate them)
        if response.failure_count > 0:
            for i, resp in enumerate(response.responses):
                if not resp.success:
                    # You could deactivate tokens here if they are invalid
                    # registration_id = tokens[i]
                    # FCMDevice.objects.filter(registration_id=registration_id).update(active=False)
                    logger.warning(f"Failed to send to token {tokens[i]}: {resp.exception}")
                    
        return response.success_count > 0
    except Exception as e:
        logger.exception(f"Error sending FCM notification: {e}")
        return False