from django.core.management.base import BaseCommand
from django.db import transaction

from others.models import AssessmentOption, AssessmentQuestion

# The question the app shipped with before questions became admin-managed.
DEFAULT_QUESTIONS = [
    {
        'text': 'What may be affecting your mood today?',
        'question_type': AssessmentQuestion.MULTIPLE_CHOICE,
        'is_required': True,
        'saves_as_tags': True,
        'options': [
            'Sleep',
            'Work/School',
            'Relationships',
            'Health',
            'Money',
            'Family',
            'Loneliness',
            'Stress',
            'Not sure',
            'Other',
        ],
    },
]


class Command(BaseCommand):
    help = (
        'Create the default assessment questions. Does nothing if any question '
        'already exists (active or not), so it is safe to run on every deploy.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if AssessmentQuestion.objects.exists():
            self.stdout.write('Assessment questions already exist; skipping.')
            return

        for order, data in enumerate(DEFAULT_QUESTIONS):
            labels = data.pop('options')
            question = AssessmentQuestion.objects.create(order=order, **data)
            AssessmentOption.objects.bulk_create(
                AssessmentOption(question=question, label=label, order=i)
                for i, label in enumerate(labels)
            )

        self.stdout.write(self.style.SUCCESS(f'Created {len(DEFAULT_QUESTIONS)} assessment question(s).'))
