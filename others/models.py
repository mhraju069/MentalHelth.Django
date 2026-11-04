from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

# Create your models here.

def mood_label_for_rating(rating):
    """Map a 0–10 mood rating onto the five mood labels used by analytics."""
    if rating >= 8:
        return 'excellent'
    if rating >= 6:
        return 'good'
    if rating >= 4:
        return 'neutral'
    if rating >= 2:
        return 'sad'
    return 'depressed'


class DailyReport(models.Model):
    LIST= (('excellent', 'Excellent'),('good', 'Good'),('neutral', 'Neutral'),('sad', 'Sad'),('depressed', 'Depressed'),)
    QUICK = 'quick'
    DETAILED = 'detailed'
    CHECK_IN_TYPES = ((QUICK, 'Quick check-in'), (DETAILED, 'Detailed assessment'))
    SLEEP_QUALITY = (('poor', 'Poor'), ('okay', 'Okay'), ('good', 'Good'), ('great', 'Great'))
    RATING_VALIDATORS = [MinValueValidator(0), MaxValueValidator(10)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='checkins')
    check_in_type = models.CharField(max_length=20, choices=CHECK_IN_TYPES, default=DETAILED)
    # Derived from mood_rating when one is given (older app versions send
    # the label directly).
    assesment = models.CharField(max_length=100, choices=LIST, blank=True)
    mood_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING_VALIDATORS)
    anxiety_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING_VALIDATORS)
    sleep_hours = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    sleep_quality = models.CharField(max_length=10, choices=SLEEP_QUALITY, blank=True, default='')
    time = models.DateTimeField(default=timezone.now)
    journal = models.TextField(blank=True)
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
        if self.mood_rating is not None:
            self.assesment = mood_label_for_rating(self.mood_rating)
            self.score = self.mood_rating
        elif self.assesment == 'excellent':
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