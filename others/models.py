from django.db import models
from django.conf import settings
import uuid

# Create your models here.

class DailyReport(models.Model):
    LIST= (('excellent', 'Excellent'),('good', 'Good'),('neutral', 'Neutral'),('sad', 'Sad'),('depressed', 'Depressed'),)
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='checkins')
    assesment = models.CharField(max_length=100, choices=LIST)
    time = models.DateTimeField()
    journal = models.TextField()
    tags = models.JSONField(default=list)
    # Answers to the admin-managed assessment questions, stored as a
    # snapshot ({question_id, question, type, answer}) so history still
    # reads correctly after a question is edited or removed.
    answers = models.JSONField(default=list, blank=True)
    score = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.time} - {self.assesment}"

    def save(self, *args, **kwargs):
        if self.assesment == 'excellent':
            self.score = 10
        elif self.assesment == 'good':
            self.score = 8
        elif self.assesment == 'neutral':
            self.score = 6
        elif self.assesment == 'sad':
            self.score = 4
        elif self.assesment == 'depressed':
            self.score = 2
        super().save(*args, **kwargs)


class AssessmentQuestion(models.Model):
    """
    A question shown in the daily check-in (Assessment step 2). Managed
    from the admin so questions can change without an app update.
    """
    SINGLE_CHOICE = 'single_choice'
    MULTIPLE_CHOICE = 'multiple_choice'
    TEXT = 'text'
    TYPES = (
        (SINGLE_CHOICE, 'Single choice'),
        (MULTIPLE_CHOICE, 'Multiple choice'),
        (TEXT, 'Short text'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.CharField(max_length=255)
    help_text = models.CharField(max_length=255, blank=True, help_text='Optional hint shown under the question.')
    question_type = models.CharField(max_length=20, choices=TYPES, default=MULTIPLE_CHOICE)
    is_required = models.BooleanField(default=True)
    saves_as_tags = models.BooleanField(
        default=False,
        help_text='Also save the selected options as check-in tags (shown in journal history).',
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text='Inactive questions are hidden from the app.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('order', 'created_at')

    def __str__(self):
        return self.text

    @property
    def is_choice(self):
        return self.question_type in (self.SINGLE_CHOICE, self.MULTIPLE_CHOICE)


class AssessmentOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE, related_name='options')
    label = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('order', 'label')

    def __str__(self):
        return self.label


class AIChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AIChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AIChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=(('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')))
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Feedback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    feedback = models.TextField()
    stars = models.CharField(max_length=10, default='1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} - {self.stars} stars - {self.created_at}"


class FCMDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fcm_devices')
    registration_id = models.TextField(unique=True)
    device_id = models.CharField(max_length=255, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.registration_id[:20]}"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.title}"