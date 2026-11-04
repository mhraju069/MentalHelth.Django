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


class Questionnaire(models.Model):
    """
    A set of questions: the daily check-in's step 2, or a standalone
    instrument such as PHQ-9. Everything about it lives in the database,
    so questionnaires can be added or changed without an app update.
    """
    DAILY_KEY = 'daily-checkin'
    SCORING_NONE = 'none'
    SCORING_SUM = 'sum'
    SCORING_CHOICES = (
        (SCORING_NONE, 'Not scored'),
        (SCORING_SUM, 'Sum of answer values'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(
        max_length=50, unique=True,
        help_text='Stable identifier used by the app and analytics, e.g. "phq-9". Do not change it once in use.',
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    instructions = models.CharField(
        max_length=255, blank=True,
        help_text='Shown above the questions, e.g. "Over the last 2 weeks, how often have you been bothered by…"',
    )
    is_daily = models.BooleanField(
        default=False, help_text='Its questions appear in step 2 of the daily check-in.',
    )
    is_locked = models.BooleanField(
        default=False,
        help_text='Validated instrument: questions, answers and scoring cannot be edited in the admin.',
    )
    scoring = models.CharField(max_length=20, choices=SCORING_CHOICES, default=SCORING_NONE)
    severity_bands = models.JSONField(
        default=list, blank=True,
        help_text='Score ranges, e.g. [{"min": 0, "max": 4, "label": "Minimal"}, {"min": 5, "max": 9, "label": "Mild"}]',
    )
    frequency_days = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='How often users are asked to complete it, e.g. 14. Empty = any time.',
    )
    copyright_notice = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('order', 'name')

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        bands = self.severity_bands or []
        if not isinstance(bands, list) or not all(
            isinstance(b, dict) and isinstance(b.get('min'), int) and isinstance(b.get('max'), int)
            and b['min'] <= b['max'] and isinstance(b.get('label'), str) and b['label']
            for b in bands
        ):
            raise ValidationError({
                'severity_bands': 'Use a list like [{"min": 0, "max": 4, "label": "Minimal"}] with whole-number ranges.',
            })

    def severity_for(self, score):
        for band in self.severity_bands or []:
            if band.get('min', float('-inf')) <= score <= band.get('max', float('inf')):
                return band.get('label', '')
        return ''


class AssessmentQuestion(models.Model):
    """
    A question in a questionnaire. Managed from the admin so questions can
    change without an app update.
    """
    SINGLE_CHOICE = 'single_choice'
    MULTIPLE_CHOICE = 'multiple_choice'
    SCALE = 'scale'
    TEXT = 'text'
    TYPES = (
        (SINGLE_CHOICE, 'Single choice'),
        (MULTIPLE_CHOICE, 'Multiple choice'),
        (SCALE, 'Scored scale (one answer; every option has a value)'),
        (TEXT, 'Short text'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    questionnaire = models.ForeignKey(
        Questionnaire, null=True, blank=True, on_delete=models.PROTECT, related_name='questions',
    )
    key = models.SlugField(
        max_length=50, blank=True, default='',
        help_text='Stable identifier within the questionnaire, e.g. "phq9-item-1". Filled in automatically if empty.',
    )
    # Goes up when the wording or answers change after people have
    # answered, so every saved answer records which version was asked.
    version = models.PositiveIntegerField(default=1, editable=False)
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
        return self.question_type != self.TEXT

    def clean(self):
        from django.core.exceptions import ValidationError
        if self._state.adding and self.questionnaire_id and self.questionnaire.is_locked:
            raise ValidationError('This questionnaire is a locked, validated instrument; questions cannot be added.')

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self._unique_key()
        super().save(*args, **kwargs)

    def _unique_key(self):
        from django.utils.text import slugify
        base = slugify(self.text)[:44] or 'question'
        siblings = AssessmentQuestion.objects.filter(questionnaire_id=self.questionnaire_id).exclude(pk=self.pk)
        key, n = base, 2
        while siblings.filter(key=key).exists():
            key, n = f'{base}-{n}', n + 1
        return key


class AssessmentOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE, related_name='options')
    label = models.CharField(max_length=100)
    value = models.IntegerField(
        null=True, blank=True, help_text='Score for this answer. Required for scored scales.',
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('order', 'label')

    def __str__(self):
        return self.label


class AssessmentResponse(models.Model):
    """
    One completed questionnaire. The daily check-in's step 2 answers are
    recorded here too (linked to the check-in), so every answer can be
    queried the same way for trends.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assessment_responses')
    # PROTECT: a questionnaire with saved answers can be deactivated but
    # never deleted, so no one's history disappears.
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.PROTECT, related_name='responses')
    daily_report = models.OneToOneField(
        DailyReport, null=True, blank=True, on_delete=models.CASCADE, related_name='assessment_response',
    )
    total_score = models.IntegerField(null=True, blank=True)
    severity = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user} - {self.questionnaire} - {self.created_at:%Y-%m-%d}'


class AssessmentResponseItem(models.Model):
    """
    One answer, with a copy of the question as it was asked (text, type,
    version), so history keeps its meaning after a question changes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    response = models.ForeignKey(AssessmentResponse, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(
        AssessmentQuestion, null=True, blank=True, on_delete=models.SET_NULL, related_name='response_items',
    )
    question_key = models.CharField(max_length=50, blank=True, default='')
    question_version = models.PositiveIntegerField(default=1)
    question_text = models.CharField(max_length=255)
    question_type = models.CharField(max_length=20)
    answer = models.JSONField()
    value = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f'{self.question_text}: {self.answer}'


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