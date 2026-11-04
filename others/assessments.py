"""
Answer validation, scoring and storage shared by the daily check-in and
standalone questionnaires (PHQ-9 and friends).
"""
from django.db import transaction
from django.db.models import Prefetch, Q
from rest_framework import serializers

from .models import AssessmentOption, AssessmentQuestion, AssessmentResponse, AssessmentResponseItem, Questionnaire


def active_questions(questions):
    """Active questions with only their active options, in display order."""
    return questions.filter(is_active=True).prefetch_related(
        Prefetch('options', queryset=AssessmentOption.objects.filter(is_active=True))
    )


def daily_questions():
    # Questions without a questionnaire predate questionnaires; they belong
    # to the daily check-in (setup_assessments links them on deploy).
    return active_questions(
        AssessmentQuestion.objects.filter(Q(questionnaire__is_daily=True) | Q(questionnaire__isnull=True))
    )


def clean_answer(question, answer):
    """
    Validate one answer. Returns (answer, value): the cleaned answer, or
    None when unanswered, and its score from the option values, if any.
    """
    if answer in (None, '', []):
        return None, None

    if question.question_type == AssessmentQuestion.TEXT:
        if not isinstance(answer, str):
            raise serializers.ValidationError(f'Invalid answer for: {question.text}')
        return (answer.strip()[:1000] or None), None

    labels = answer if isinstance(answer, list) else [answer]
    if not all(isinstance(label, str) for label in labels):
        raise serializers.ValidationError(f'Invalid answer for: {question.text}')
    options = {o.label: o for o in question.options.all()}
    if any(label not in options for label in labels):
        raise serializers.ValidationError(f'Invalid option for: {question.text}')

    if question.question_type == AssessmentQuestion.MULTIPLE_CHOICE:
        labels = list(dict.fromkeys(labels))
        values = [options[label].value for label in labels if options[label].value is not None]
        return labels, (sum(values) if values else None)

    if len(labels) > 1:
        raise serializers.ValidationError(f'Choose only one option for: {question.text}')
    return labels[0], options[labels[0]].value


def build_items(questions, submitted):
    """
    Check submitted [{"question_id", "answer"}] against the given (active)
    questions and return answer snapshots in question order. Raises a
    ValidationError for unknown questions, bad answers or missing required
    answers.
    """
    by_id = {str(q.id): q for q in questions}
    answers = {}
    for item in submitted:
        question_id = str(item.get('question_id', ''))
        if question_id not in by_id:
            raise serializers.ValidationError('This question is no longer available. Please refresh and try again.')
        answers[question_id] = item.get('answer')

    items = []
    for question_id, question in by_id.items():
        answer, value = clean_answer(question, answers.get(question_id))
        if answer is None:
            if question.is_required:
                raise serializers.ValidationError(f'Please answer: {question.text}')
            continue
        items.append({
            'question_id': question_id,
            'key': question.key,
            'version': question.version,
            'question': question.text,
            'type': question.question_type,
            'answer': answer,
            'value': value,
        })
    return items


def max_score(questionnaire):
    """Highest possible total: the top option value of each active scored item."""
    total = 0
    for question in questionnaire.questions.filter(is_active=True, question_type=AssessmentQuestion.SCALE):
        values = [o.value for o in question.options.all() if o.is_active and o.value is not None]
        total += max(values, default=0)
    return total


def score(questionnaire, items):
    """(total_score, severity) for a questionnaire's answers."""
    if questionnaire.scoring != Questionnaire.SCORING_SUM:
        return None, ''
    total = sum(item['value'] for item in items if item.get('value') is not None)
    return total, questionnaire.severity_for(total)


@transaction.atomic
def save_response(user, questionnaire, items, daily_report=None, created_at=None):
    total, severity = score(questionnaire, items)
    thresholds = {
        str(pk): threshold for pk, threshold in AssessmentQuestion.objects.filter(
            pk__in=[item['question_id'] for item in items]
        ).values_list('pk', 'safety_threshold')
    }
    question_ids = set(thresholds)
    needs_safety_followup = any(
        thresholds.get(item['question_id']) is not None
        and item.get('value') is not None
        and item['value'] >= thresholds[item['question_id']]
        for item in items
    )
    response = AssessmentResponse.objects.create(
        user=user,
        questionnaire=questionnaire,
        daily_report=daily_report,
        total_score=total,
        severity=severity,
        needs_safety_followup=needs_safety_followup,
        **({'created_at': created_at} if created_at else {}),
    )
    AssessmentResponseItem.objects.bulk_create(
        AssessmentResponseItem(
            response=response,
            # The question may have been deleted since (older snapshots).
            question_id=item['question_id'] if item['question_id'] in question_ids else None,
            question_key=item.get('key', ''),
            question_version=item.get('version', 1),
            question_text=item['question'],
            question_type=item['type'],
            answer=item['answer'],
            value=item.get('value'),
        )
        for item in items
    )
    return response


def record_daily_response(report):
    """
    Store a check-in's step 2 answers (its `answers` snapshot) as a
    response of the daily questionnaire. Safe to call more than once.
    """
    if not report.answers or AssessmentResponse.objects.filter(daily_report=report).exists():
        return None
    daily = Questionnaire.objects.filter(is_daily=True).first()
    if daily is None:
        return None
    # Snapshots saved before questionnaires existed lack key/version.
    keys = dict(
        AssessmentQuestion.objects.filter(
            pk__in=[a.get('question_id') for a in report.answers if a.get('question_id')]
        ).values_list('pk', 'key')
    )
    items = [
        {**answer, 'key': answer.get('key') or keys.get(_as_uuid(answer.get('question_id')), '')}
        for answer in report.answers
    ]
    return save_response(report.user, daily, items, daily_report=report, created_at=report.created_at)


def _as_uuid(value):
    import uuid
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
