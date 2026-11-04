from django.core.management.base import BaseCommand
from django.db import transaction

from others.assessments import record_daily_response
from others.models import AssessmentOption, AssessmentQuestion, DailyReport, Questionnaire

# The question the app shipped with before questions became admin-managed.
DEFAULT_DAILY_QUESTIONS = [
    {
        'key': 'mood-factors',
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
        'Bring assessment data up to date; safe to run on every deploy. Creates the daily '
        'check-in questionnaire, attaches questions created before questionnaires existed, '
        'adds the default question to an empty database, and copies check-in answers that '
        'are not yet in the responses table.'
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            daily, created = Questionnaire.objects.get_or_create(
                key=Questionnaire.DAILY_KEY,
                defaults={'name': 'Daily check-in', 'is_daily': True},
            )
            if created:
                self.stdout.write('Created the daily check-in questionnaire.')

            linked = AssessmentQuestion.objects.filter(questionnaire__isnull=True).update(questionnaire=daily)
            if linked:
                self.stdout.write(f'Linked {linked} existing question(s) to the daily check-in.')

            # Only for a brand-new database: once any question exists (active
            # or not), admins own the list. Deactivate instead of deleting.
            if not AssessmentQuestion.objects.exists():
                for order, data in enumerate(DEFAULT_DAILY_QUESTIONS):
                    data = dict(data)
                    labels = data.pop('options')
                    question = AssessmentQuestion.objects.create(questionnaire=daily, order=order, **data)
                    AssessmentOption.objects.bulk_create(
                        AssessmentOption(question=question, label=label, order=i)
                        for i, label in enumerate(labels)
                    )
                self.stdout.write(f'Created {len(DEFAULT_DAILY_QUESTIONS)} default question(s).')

            # Questions saved before keys existed.
            for question in AssessmentQuestion.objects.filter(key=''):
                question.save()

        pending = (
            DailyReport.objects.exclude(answers=[])
            .filter(assessment_response__isnull=True)
            .select_related('user')
        )
        copied = sum(1 for report in pending.iterator() if record_daily_response(report))
        if copied:
            self.stdout.write(f'Copied answers from {copied} check-in(s) into the responses table.')

        self.stdout.write(self.style.SUCCESS('Assessments are up to date.'))
