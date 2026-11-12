from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from .assessments import record_daily_response
from .models import (
    AssessmentOption, AssessmentQuestion, AssessmentResponse, AssessmentResponseItem, DailyReport, Questionnaire,
)


class AssessmentQuestionTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='user@example.com', password='pass12345')
        self.client.force_authenticate(self.user)

        self.factors = AssessmentQuestion.objects.create(
            text='What may be affecting your mood today?',
            question_type=AssessmentQuestion.MULTIPLE_CHOICE,
            saves_as_tags=True,
            order=0,
        )
        for i, label in enumerate(['Sleep', 'Work/School', 'Stress']):
            AssessmentOption.objects.create(question=self.factors, label=label, order=i)
        AssessmentOption.objects.create(question=self.factors, label='Hidden', is_active=False)

        self.energy = AssessmentQuestion.objects.create(
            text='Energy level?', question_type=AssessmentQuestion.SINGLE_CHOICE, order=1,
        )
        for label in ['Low', 'High']:
            AssessmentOption.objects.create(question=self.energy, label=label)

        self.note = AssessmentQuestion.objects.create(
            text='Anything else?', question_type=AssessmentQuestion.TEXT, is_required=False, order=2,
        )
        AssessmentQuestion.objects.create(text='Retired question', is_active=False)

    def checkin(self, **extra):
        payload = {
            'assesment': 'good',
            'time': '2026-11-03T10:00:00Z',
            'journal': 'Today was fine.',
            **extra,
        }
        return self.client.post('/api/checkin/', payload, format='json')

    def test_lists_only_active_questions_and_options_in_order(self):
        response = self.client.get('/api/assessment/questions/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([q['text'] for q in response.data], ['What may be affecting your mood today?', 'Energy level?', 'Anything else?'])
        self.assertEqual([o['label'] for o in response.data[0]['options']], ['Sleep', 'Work/School', 'Stress'])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/assessment/questions/').status_code, 401)

    def test_checkin_saves_answer_snapshot_and_derives_tags(self):
        response = self.checkin(answers=[
            {'question_id': str(self.factors.id), 'answer': ['Stress', 'Sleep']},
            {'question_id': str(self.energy.id), 'answer': 'Low'},
            {'question_id': str(self.note.id), 'answer': '  tired  '},
        ], tags=['ignored'])

        self.assertEqual(response.status_code, 201, response.data)
        report = DailyReport.objects.get()
        self.assertEqual(report.tags, ['Stress', 'Sleep'])
        self.assertEqual(
            [(a['question'], a['answer']) for a in report.answers],
            [('What may be affecting your mood today?', ['Stress', 'Sleep']), ('Energy level?', 'Low'), ('Anything else?', 'tired')],
        )

    def test_missing_required_answer_is_rejected(self):
        response = self.checkin(answers=[{'question_id': str(self.factors.id), 'answer': ['Sleep']}])

        self.assertEqual(response.status_code, 400)
        self.assertIn('Energy level?', str(response.data))

    def test_invalid_answers_are_rejected(self):
        cases = [
            [{'question_id': str(self.factors.id), 'answer': ['Hidden']}],
            [{'question_id': str(self.energy.id), 'answer': ['Low', 'High']}],
            [{'question_id': '00000000-0000-0000-0000-000000000000', 'answer': 'x'}],
        ]
        for answers in cases:
            with self.subTest(answers=answers):
                self.assertEqual(self.checkin(answers=answers).status_code, 400)

    def test_old_app_versions_can_still_send_tags_only(self):
        response = self.checkin(tags=['Sleep'])

        self.assertEqual(response.status_code, 201, response.data)
        report = DailyReport.objects.get()
        self.assertEqual(report.tags, ['Sleep'])
        self.assertEqual(report.answers, [])


class RatedCheckinTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='rated@example.com', password='pass12345')
        self.client.force_authenticate(self.user)

    def checkin(self, **payload):
        return self.client.post('/api/checkin/', payload, format='json')

    def test_quick_checkin_needs_only_mood_and_anxiety(self):
        response = self.checkin(check_in_type='quick', mood_rating=3, anxiety_rating=8)

        self.assertEqual(response.status_code, 201, response.data)
        report = DailyReport.objects.get()
        self.assertEqual((report.assesment, report.score, report.journal), ('sad', 3, ''))
        self.assertIsNotNone(report.time)

    def test_detailed_checkin_requires_sleep(self):
        response = self.checkin(check_in_type='detailed', mood_rating=7, anxiety_rating=2)
        self.assertEqual(response.status_code, 400)
        self.assertIn('sleep_hours', response.data)

        response = self.checkin(
            check_in_type='detailed', mood_rating=7, anxiety_rating=2,
            sleep_hours='7.5', sleep_quality='good', journal='Nice walk.',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(DailyReport.objects.get().assesment, 'good')

    def test_rejects_out_of_range_values(self):
        for extra in ({'mood_rating': 11}, {'anxiety_rating': -1}, {'sleep_hours': '7.3'}, {'sleep_hours': '25'}):
            with self.subTest(extra=extra):
                payload = {'check_in_type': 'quick', 'mood_rating': 5, 'anxiety_rating': 5, **extra}
                self.assertEqual(self.checkin(**payload).status_code, 400)

    def test_mood_label_boundaries(self):
        from .models import mood_label_for_rating
        self.assertEqual(
            [mood_label_for_rating(r) for r in range(11)],
            ['depressed', 'depressed', 'sad', 'sad', 'neutral', 'neutral', 'good', 'good', 'excellent', 'excellent', 'excellent'],
        )

    def test_multiple_checkins_a_day_notify_streak_once(self):
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone

        now = timezone.now()
        for days_ago in (2, 1):
            report = DailyReport.objects.create(user=self.user, mood_rating=5, anxiety_rating=5)
            DailyReport.objects.filter(pk=report.pk).update(created_at=now - timedelta(days=days_ago))

        with patch('others.views.send_streak_notification') as task:
            self.checkin(check_in_type='quick', mood_rating=5, anxiety_rating=5)
            self.checkin(check_in_type='quick', mood_rating=6, anxiety_rating=4)

        self.assertEqual(DailyReport.objects.count(), 4)
        task.delay.assert_called_once_with(str(self.user.id), 3)

    def test_ai_context_summarises_recent_checkins_without_journal(self):
        from .views import AIChatSendMessageView

        DailyReport.objects.create(
            user=self.user, check_in_type='detailed', mood_rating=4, anxiety_rating=7,
            sleep_hours='5.5', sleep_quality='poor', tags=['Work/School'], journal='private words',
        )
        summary = AIChatSendMessageView._checkin_summary(self.user)

        self.assertIn('mood 4/10; anxiety 7/10; slept 5.5h (poor); factors: Work/School', summary)
        self.assertNotIn('private words', summary)
        self.assertIsNone(AIChatSendMessageView._checkin_summary(get_user_model().objects.create_user(email='new@example.com')))


class AnalyticsAccuracyTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='stats@example.com', password='pass12345')
        self.client.force_authenticate(self.user)

    def add(self, created_at, **fields):
        report = DailyReport.objects.create(user=self.user, **fields)
        DailyReport.objects.filter(pk=report.pk).update(created_at=created_at)
        return report

    def test_average_mixes_labels_and_ratings_on_one_scale(self):
        from django.utils import timezone

        now = timezone.now()
        self.add(now, assesment='good')            # legacy label → 8
        self.add(now, mood_rating=3, anxiety_rating=5)  # rating → 3
        response = self.client.get('/api/insights/')

        self.assertEqual(response.data['entries'], 2)
        self.assertEqual(response.data['average_mood'], '5.5/10')
        summary = {item['assesment']: item['count'] for item in response.data['summary']}
        self.assertEqual((summary['good'], summary['sad']), (1, 1))

    def test_buckets_by_when_checked_in_not_the_picked_start_time(self):
        from datetime import timedelta
        from django.utils import timezone

        # Older app versions sent a user-picked "when did this start" date.
        self.add(timezone.now(), assesment='sad', time=timezone.now() - timedelta(days=60))
        self.assertEqual(self.client.get('/api/insights/').data['entries'], 1)

    def test_days_follow_the_users_timezone(self):
        from datetime import datetime, timedelta, timezone as dt_timezone
        from unittest.mock import patch

        # Morning and evening of Nov 4 in New York; the evening one is
        # already Nov 5 in UTC.
        morning = datetime(2026, 11, 4, 13, 0, tzinfo=dt_timezone.utc)  # 08:00 NY
        evening = datetime(2026, 11, 5, 2, 0, tzinfo=dt_timezone.utc)   # 21:00 NY
        self.add(morning, mood_rating=5, anxiety_rating=5)
        self.add(evening, mood_rating=5, anxiety_rating=5)

        with patch('django.utils.timezone.now', return_value=evening + timedelta(minutes=30)):
            ny = self.client.get('/api/report/', HTTP_X_TIMEZONE='America/New_York').data
            utc = self.client.get('/api/report/').data
            bad = self.client.get('/api/report/', HTTP_X_TIMEZONE='Not/AZone')

        self.assertEqual(ny['streak'], 1)   # one day in New York
        self.assertEqual(utc['streak'], 2)  # two days in UTC
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.data['streak'], 2)

    def test_trend_needs_last_month_to_compare(self):
        from django.utils import timezone

        self.add(timezone.now(), mood_rating=7, anxiety_rating=3)
        self.assertEqual(self.client.get('/api/insights/').data['mood_trend'], '--')

    def test_insights_include_anxiety_sleep_daily_and_factors(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        # Stay inside the current month whatever day the test runs.
        earlier = now - timedelta(days=1) if now.day > 1 else now
        self.add(earlier, mood_rating=4, anxiety_rating=8, sleep_hours='5.5', tags=['Work/School', 'Stress'])
        self.add(now, mood_rating=8, anxiety_rating=2, sleep_hours='8', tags=['Stress'])
        self.add(now, assesment='good', tags=['Family'])  # legacy: no anxiety/sleep

        data = self.client.get('/api/insights/').data

        self.assertEqual((data['average_anxiety'], data['average_sleep']), (5.0, 6.8))
        self.assertEqual(data['top_factors'][0], {'factor': 'Stress', 'count': 2})
        self.assertEqual(len(data['top_factors']), 3)
        self.assertEqual(data['daily'][-1]['date'], timezone.localdate().isoformat())
        self.assertEqual(data['daily'][-1]['anxiety'], 2.0)
        self.assertEqual(data['daily'][-1]['mood'], 8.0)  # (8 + legacy "good" 8) / 2

    def test_insights_without_new_fields_return_none(self):
        from django.utils import timezone

        self.add(timezone.now(), assesment='sad')
        data = self.client.get('/api/insights/').data
        self.assertEqual((data['average_anxiety'], data['average_sleep'], data['top_factors']), (None, None, []))


class SetupAssessmentsTests(APITestCase):
    def run_setup(self):
        call_command('setup_assessments', stdout=StringIO())

    def test_seeds_default_question_once_into_daily_questionnaire(self):
        self.run_setup()
        self.run_setup()

        question = AssessmentQuestion.objects.get(questionnaire__is_daily=True)
        self.assertEqual(question.key, 'mood-factors')
        self.assertTrue(question.saves_as_tags)
        self.assertEqual(question.options.count(), 10)

    def test_links_existing_questions_and_backfills_old_answers(self):
        user = get_user_model().objects.create_user(email='old@example.com', password='pass12345')
        legacy = AssessmentQuestion.objects.create(text='Energy level?', question_type='single_choice')
        report = DailyReport.objects.create(
            user=user, assesment='good',
            # Snapshot format from before questionnaires (no key/version/value).
            answers=[{'question_id': str(legacy.id), 'question': 'Energy level?', 'type': 'single_choice', 'answer': 'Low'}],
        )
        DailyReport.objects.create(user=user, assesment='sad')  # no answers: nothing to copy

        self.run_setup()
        self.run_setup()

        legacy.refresh_from_db()
        self.assertEqual(legacy.questionnaire.key, Questionnaire.DAILY_KEY)
        self.assertEqual(legacy.key, 'energy-level')
        response = AssessmentResponse.objects.get()
        self.assertEqual((response.daily_report, response.user, response.created_at), (report, user, report.created_at))
        item = response.items.get()
        self.assertEqual((item.question, item.question_key, item.question_version, item.answer), (legacy, 'energy-level', 1, 'Low'))


class QuestionnaireApiTests(APITestCase):
    def setUp(self):
        call_command('setup_assessments', stdout=StringIO())
        self.user = get_user_model().objects.create_user(email='q@example.com', password='pass12345')
        self.client.force_authenticate(self.user)

        self.screen = Questionnaire.objects.create(
            key='mini-screen', name='Mini screen', scoring=Questionnaire.SCORING_SUM, frequency_days=14,
            severity_bands=[{'min': 0, 'max': 2, 'label': 'Minimal'}, {'min': 3, 'max': 6, 'label': 'Moderate'}],
        )
        self.items = []
        for i, text in enumerate(['Little interest?', 'Feeling down?']):
            question = AssessmentQuestion.objects.create(
                questionnaire=self.screen, text=text, question_type=AssessmentQuestion.SCALE, order=i,
            )
            for value, label in enumerate(['Not at all', 'Several days', 'More than half the days', 'Nearly every day']):
                AssessmentOption.objects.create(question=question, label=label, value=value, order=value)
            self.items.append(question)

    def answer(self, *labels):
        return [{'question_id': str(q.id), 'answer': label} for q, label in zip(self.items, labels)]

    def test_lists_standalone_questionnaires_with_due_status(self):
        data = self.client.get('/api/assessments/').data
        mini = lambda data: next(q for q in data if q['key'] == 'mini-screen')
        data = self.client.get('/api/assessments/').data
        self.assertNotIn(Questionnaire.DAILY_KEY, [q['key'] for q in data])
        self.assertEqual((mini(data)['is_due'], mini(data)['last_completed_at']), (True, None))

        self.client.post('/api/assessments/mini-screen/responses/', {'answers': self.answer('Not at all', 'Not at all')}, format='json')
        data = self.client.get('/api/assessments/').data
        self.assertFalse(mini(data)['is_due'])
        self.assertIsNotNone(mini(data)['next_due_at'])

    def test_detail_returns_questions_with_scored_options(self):
        data = self.client.get('/api/assessments/mini-screen/').data
        self.assertEqual([q['text'] for q in data['questions']], ['Little interest?', 'Feeling down?'])
        self.assertEqual([o['value'] for o in data['questions'][0]['options']], [0, 1, 2, 3])

    def test_submission_is_scored_and_kept_in_history(self):
        response = self.client.post(
            '/api/assessments/mini-screen/responses/',
            {'answers': self.answer('Several days', 'More than half the days')}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['total_score'], response.data['severity']), (3, 'Moderate'))
        self.assertEqual([i['value'] for i in response.data['items']], [1, 2])

        history = self.client.get('/api/assessments/mini-screen/responses/').data
        self.assertEqual([r['total_score'] for r in history], [3])

    def test_rejects_incomplete_or_invalid_submissions(self):
        url = '/api/assessments/mini-screen/responses/'
        self.assertEqual(self.client.post(url, {'answers': self.answer('Several days')}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'answers': self.answer('Several days', 'Always')}, format='json').status_code, 400)
        self.assertEqual(AssessmentResponse.objects.count(), 0)

    def test_daily_and_inactive_questionnaires_are_not_standalone(self):
        self.assertEqual(self.client.get(f'/api/assessments/{Questionnaire.DAILY_KEY}/').status_code, 404)
        Questionnaire.objects.filter(pk=self.screen.pk).update(is_active=False)
        self.assertEqual(self.client.get('/api/assessments/mini-screen/').status_code, 404)

    def test_checkin_answers_are_recorded_as_a_daily_response(self):
        factors = AssessmentQuestion.objects.get(key='mood-factors')
        response = self.client.post('/api/checkin/', {
            'check_in_type': 'detailed', 'mood_rating': 6, 'anxiety_rating': 4, 'sleep_hours': 7, 'sleep_quality': 'good',
            'answers': [{'question_id': str(factors.id), 'answer': ['Stress']}],
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        daily = AssessmentResponse.objects.get(questionnaire__is_daily=True)
        self.assertEqual(daily.daily_report_id, DailyReport.objects.get().id)
        self.assertEqual(list(daily.items.values_list('question_key', 'answer')), [('mood-factors', ['Stress'])])


class InstrumentMixin:
    """Seeded PHQ-9/GAD-7, a signed-in user, and a quick way to submit them."""

    def setUp(self):
        call_command('setup_assessments', stdout=StringIO())
        self.user = get_user_model().objects.create_user(email='phq@example.com', password='pass12345')
        self.client.force_authenticate(self.user)

    def submit(self, key, item_answer, last_item=None, difficulty=None):
        questions = self.client.get(f'/api/assessments/{key}/').data['questions']
        scored = [q for q in questions if q['question_type'] == 'scale']
        answers = [{'question_id': q['id'], 'answer': item_answer} for q in scored]
        if last_item:
            answers[-1]['answer'] = last_item
        if difficulty:
            answers.append({'question_id': questions[-1]['id'], 'answer': difficulty})
        return self.client.post(f'/api/assessments/{key}/responses/', {'answers': answers}, format='json')


class ValidatedInstrumentTests(InstrumentMixin, APITestCase):
    def test_instruments_are_seeded_locked_with_published_structure(self):
        phq9 = Questionnaire.objects.get(key='phq-9')
        gad7 = Questionnaire.objects.get(key='gad-7')
        self.assertTrue(phq9.is_locked and gad7.is_locked)
        self.assertEqual(phq9.questions.filter(question_type='scale').count(), 9)
        self.assertEqual(gad7.questions.filter(question_type='scale').count(), 7)
        self.assertEqual(
            list(phq9.questions.get(key='phq9-1').options.values_list('label', 'value')),
            [('Not at all', 0), ('Several days', 1), ('More than half the days', 2), ('Nearly every day', 3)],
        )
        # Re-running setup never duplicates or alters them.
        call_command('setup_assessments', stdout=StringIO())
        self.assertEqual(Questionnaire.objects.filter(key='phq-9').count(), 1)

    def test_phq9_scores_and_severity(self):
        for answer, total, severity in [
            ('Not at all', 0, 'Minimal'), ('Several days', 9, 'Mild'),
            ('More than half the days', 18, 'Moderately severe'), ('Nearly every day', 27, 'Severe'),
        ]:
            with self.subTest(answer=answer):
                response = self.submit('phq-9', answer)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual((response.data['total_score'], response.data['severity']), (total, severity))

    def test_gad7_scores_and_difficulty_is_optional_and_unscored(self):
        response = self.submit('gad-7', 'Nearly every day', difficulty='Very difficult')
        self.assertEqual((response.data['total_score'], response.data['severity']), (21, 'Severe'))
        self.assertEqual(response.data['items'][-1]['value'], None)

    def test_phq9_item_9_flags_safety_followup(self):
        flagged = self.submit('phq-9', 'Not at all', last_item='Several days')
        self.assertTrue(flagged.data['needs_safety_followup'])
        self.assertEqual(flagged.data['total_score'], 1)

        clear = self.submit('phq-9', 'Nearly every day', last_item='Not at all')
        self.assertFalse(clear.data['needs_safety_followup'])


class TrendTests(InstrumentMixin, APITestCase):
    def age(self, days):
        from datetime import timedelta
        from django.utils import timezone
        latest = AssessmentResponse.objects.latest('created_at')
        AssessmentResponse.objects.filter(pk=latest.pk).update(created_at=timezone.now() - timedelta(days=days))

    def test_trends_list_results_oldest_first_with_max_score(self):
        self.submit('phq-9', 'More than half the days')  # 18
        self.age(30)
        self.submit('phq-9', 'Several days')             # 9, today
        self.submit('gad-7', 'Not at all')
        self.age(400)                                    # too old for the 6-month window

        data = {t['key']: t for t in self.client.get('/api/assessments/trends/').data}
        self.assertEqual(data['phq-9']['max_score'], 27)
        self.assertEqual(data['gad-7']['max_score'], 21)
        self.assertEqual([r['total_score'] for r in data['phq-9']['results']], [18, 9])
        self.assertEqual(data['gad-7']['results'], [])

    def test_trends_only_show_the_users_own_results(self):
        self.submit('phq-9', 'Nearly every day')
        other = get_user_model().objects.create_user(email='other@example.com', password='pass12345')
        self.client.force_authenticate(other)
        data = {t['key']: t for t in self.client.get('/api/assessments/trends/').data}
        self.assertEqual(data['phq-9']['results'], [])

    def test_ai_trend_summary_has_monthly_averages_scores_and_safety_note(self):
        from .views import AIChatSendMessageView

        DailyReport.objects.create(user=self.user, mood_rating=4, anxiety_rating=8, sleep_hours='6.5', sleep_quality='poor')
        DailyReport.objects.create(user=self.user, mood_rating=6, anxiety_rating=6, sleep_hours='7.5', sleep_quality='good')
        self.submit('phq-9', 'Several days')  # item 9 > 0 → flagged
        summary = AIChatSendMessageView._trend_summary(self.user)

        self.assertIn('2 check-ins; average mood 5.0/10; average anxiety 7.0/10; average sleep 7.0h', summary)
        self.assertIn('Mood questionnaire (PHQ-9)', summary)
        self.assertIn('score 9 (Mild)', summary)
        self.assertIn('988', summary)

    def test_ai_trend_summary_without_data_or_safety_flag(self):
        from .views import AIChatSendMessageView

        self.assertIsNone(AIChatSendMessageView._trend_summary(self.user))
        self.submit('gad-7', 'Several days')
        self.assertNotIn('988', AIChatSendMessageView._trend_summary(self.user))


class AssessmentAdminTests(APITestCase):
    def setUp(self):
        call_command('setup_assessments', stdout=StringIO())
        self.admin = get_user_model().objects.create_superuser(email='admin@example.com', password='pass12345')
        self.client.force_login(self.admin)
        self.question = AssessmentQuestion.objects.get(key='mood-factors')

    def change(self, question, **overrides):
        options = list(question.options.all())
        data = {
            'questionnaire': str(question.questionnaire_id), 'text': question.text, 'help_text': question.help_text,
            'question_type': question.question_type, 'is_required': 'on', 'saves_as_tags': 'on',
            'key': question.key, 'order': question.order, 'is_active': 'on',
            'options-TOTAL_FORMS': len(options), 'options-INITIAL_FORMS': len(options),
            'options-MIN_NUM_FORMS': 0, 'options-MAX_NUM_FORMS': 1000,
        }
        for i, option in enumerate(options):
            data.update({
                f'options-{i}-id': str(option.id), f'options-{i}-question': str(question.id),
                f'options-{i}-label': option.label, f'options-{i}-value': '',
                f'options-{i}-order': option.order, f'options-{i}-is_active': 'on',
            })
        data.update(overrides)
        return self.client.post(f'/admin/others/assessmentquestion/{question.id}/change/', data)

    def answer_once(self):
        user = get_user_model().objects.create_user(email='a@example.com', password='pass12345')
        report = DailyReport.objects.create(
            user=user, mood_rating=5, anxiety_rating=5,
            answers=[{'question_id': str(self.question.id), 'question': self.question.text, 'type': 'multiple_choice', 'answer': ['Sleep']}],
        )
        record_daily_response(report)

    def test_rewording_an_answered_question_bumps_its_version_and_keeps_old_text(self):
        self.answer_once()
        response = self.change(self.question, text='What is affecting your mood right now?')

        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        self.assertEqual((self.question.text, self.question.version), ('What is affecting your mood right now?', 2))
        self.assertEqual(AssessmentResponseItem.objects.get().question_text, 'What may be affecting your mood today?')

    def test_editing_unanswered_or_cosmetic_fields_keeps_version(self):
        self.change(self.question, text='Reworded before anyone answered')
        self.question.refresh_from_db()
        self.answer_once()
        self.change(self.question, order=5)
        self.question.refresh_from_db()
        self.assertEqual(self.question.version, 1)

    def test_answered_questions_cannot_be_deleted(self):
        self.answer_once()
        response = self.client.post(f'/admin/others/assessmentquestion/{self.question.id}/delete/', {'post': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(AssessmentQuestion.objects.filter(pk=self.question.pk).exists())

    def test_locked_questionnaire_questions_are_read_only(self):
        Questionnaire.objects.filter(is_daily=True).update(is_locked=True)
        response = self.change(self.question, text='Tampered')

        self.assertEqual(response.status_code, 403)
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, 'What may be affecting your mood today?')

    def test_admin_pages_load(self):
        self.answer_once()
        for url in [
            '/admin/others/questionnaire/',
            f'/admin/others/questionnaire/{self.question.questionnaire_id}/change/',
            '/admin/others/assessmentquestion/',
            f'/admin/others/assessmentquestion/{self.question.id}/change/',
            '/admin/others/assessmentresponse/',
            f'/admin/others/assessmentresponse/{AssessmentResponse.objects.get().id}/change/',
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class AccountDeletionTests(InstrumentMixin, APITestCase):
    """App Store 5.1.1(v): deleting the account removes it and all its data."""

    def test_delete_account_removes_user_and_all_their_data(self):
        from .models import AIChatMessage, AIChatSession, Notification

        DailyReport.objects.create(user=self.user, mood_rating=5, anxiety_rating=5, journal='private')
        self.submit('phq-9', 'Several days')
        session = AIChatSession.objects.create(user=self.user)
        AIChatMessage.objects.create(session=session, role='user', content='hello')
        Notification.objects.create(user=self.user, title='t', body='b')

        response = self.client.delete('/api/auth/user/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertEqual(DailyReport.objects.count(), 0)
        self.assertEqual(AssessmentResponse.objects.count(), 0)
        self.assertEqual(AssessmentResponseItem.objects.count(), 0)
        self.assertEqual(AIChatMessage.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        # Shared questionnaires stay for everyone else.
        self.assertTrue(Questionnaire.objects.filter(key='phq-9').exists())


class FeedbackTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='fb@example.com', password='pass12345')
        self.client.force_authenticate(self.user)

    def test_rating_must_be_1_to_5(self):
        for stars in (0, 6, 5.5, 'x'):
            with self.subTest(stars=stars):
                self.assertEqual(self.client.post('/api/feedback/', {'stars': stars, 'feedback': 'hi'}, format='json').status_code, 400)

    def test_comment_is_optional(self):
        from .models import Feedback

        response = self.client.post('/api/feedback/', {'stars': 4}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Feedback.objects.get().stars, '4')


class ReminderTimingTests(APITestCase):
    def make_user(self, email, tz, at, notify=True):
        from datetime import time
        # Active = verified; unverified sign-ups get no reminders.
        return get_user_model().objects.create_user(
            email=email, password='pass12345', timezone=tz, checkin_time=at, notify=notify, is_active=True,
        )

    def test_reminders_follow_each_users_local_time(self):
        from datetime import datetime, time, timezone as dt_timezone
        from .tasks import users_due_for_reminder

        ny = self.make_user('ny@example.com', 'America/New_York', time(21, 0))
        tokyo = self.make_user('tokyo@example.com', 'Asia/Tokyo', time(11, 0))
        self.make_user('off@example.com', 'America/New_York', time(21, 0), notify=False)
        self.make_user('utc@example.com', 'UTC', time(21, 0))

        # 02:00 UTC on Nov 5 = 21:00 Nov 4 in New York = 11:00 Nov 5 in Tokyo.
        due = users_due_for_reminder(datetime(2026, 11, 5, 2, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(set(due), {ny.id, tokyo.id})

    def test_no_reminder_after_checking_in_today(self):
        from datetime import datetime, time, timezone as dt_timezone
        from .tasks import users_due_for_reminder

        user = self.make_user('done@example.com', 'America/New_York', time(21, 0))
        now = datetime(2026, 11, 5, 2, 0, tzinfo=dt_timezone.utc)  # 21:00 Nov 4 NY
        report = DailyReport.objects.create(user=user, mood_rating=6, anxiety_rating=3)
        # Checked in at 08:00 New York time the same day.
        DailyReport.objects.filter(pk=report.pk).update(created_at=datetime(2026, 11, 4, 13, 0, tzinfo=dt_timezone.utc))

        self.assertEqual(users_due_for_reminder(now), [])

    def test_bad_timezone_falls_back_to_utc(self):
        from datetime import datetime, time, timezone as dt_timezone
        from .tasks import users_due_for_reminder

        user = self.make_user('bad@example.com', 'Not/AZone', time(2, 0))
        self.assertEqual(users_due_for_reminder(datetime(2026, 11, 5, 2, 0, tzinfo=dt_timezone.utc)), [user.id])


# ─── OpenAI credits & usage ──────────────────────────────────────────────────

from datetime import date, datetime, timedelta, timezone as dt_tz
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from . import openai_billing
from .models import OpenAIBillingSettings, OpenAICredit, OpenAIDailyUsage


def _ts(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=dt_tz.utc).timestamp())


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body, self.status_code, self.text = body, status_code, str(body)

    def json(self):
        return self._body


@override_settings(OPENAI_ADMIN_KEY='sk-admin-test', CONTACT_EMAIL='hello@example.com',
                   OPENAI_ALERT_EMAILS='dev@example.com', EMAIL_HOST_USER='app@example.com')
class OpenAIBillingTests(APITestCase):
    today = date(2026, 11, 12)

    def fake_get(self, url, headers=None, params=None, timeout=None):
        assert headers['Authorization'] == 'Bearer sk-admin-test'
        d1, d2 = self.today - timedelta(days=1), self.today
        if url.endswith('/costs'):
            if params.get('page') is None:
                return FakeResponse({'data': [{'start_time': _ts(d1), 'results': [
                    {'amount': {'value': 1.25, 'currency': 'usd'}},
                    {'amount': {'value': 0.25, 'currency': 'usd'}},
                ]}], 'has_more': True, 'next_page': 'p2'})
            return FakeResponse({'data': [{'start_time': _ts(d2), 'results': [
                {'amount': {'value': 0.5, 'currency': 'usd'}}]}], 'has_more': False})
        return FakeResponse({'data': [{'start_time': _ts(d1), 'results': [
            {'input_tokens': 1000, 'output_tokens': 200, 'num_model_requests': 7}]}], 'has_more': False})

    def test_sync_stores_daily_cost_and_tokens_across_pages(self):
        with mock.patch('others.openai_billing.requests.get', side_effect=self.fake_get):
            openai_billing.sync_usage(self.today)
        y = OpenAIDailyUsage.objects.get(date=self.today - timedelta(days=1))
        self.assertEqual(y.cost_usd, Decimal('1.5'))
        self.assertEqual((y.input_tokens, y.output_tokens, y.requests), (1000, 200, 7))
        self.assertEqual(OpenAIDailyUsage.objects.get(date=self.today).cost_usd, Decimal('0.5'))

    def test_sync_error_is_recorded_and_no_alert(self):
        OpenAICredit.objects.create(amount=1, added_on=self.today - timedelta(days=5))
        with mock.patch('others.openai_billing.requests.get',
                        return_value=FakeResponse({'error': {'message': 'bad key'}}, 401)):
            openai_billing.sync_and_check()
        self.assertIn('bad key', OpenAIBillingSettings.load().last_sync_error)
        self.assertEqual(len(mail.outbox), 0)

    def test_balance_is_credits_minus_costs_after_first_entry(self):
        OpenAICredit.objects.create(amount=20, added_on=self.today - timedelta(days=10))
        OpenAICredit.objects.create(amount=10, added_on=self.today - timedelta(days=2))
        OpenAIDailyUsage.objects.create(date=self.today - timedelta(days=10), cost_usd=5)  # before: ignored
        OpenAIDailyUsage.objects.create(date=self.today - timedelta(days=3), cost_usd=7)
        OpenAIDailyUsage.objects.create(date=self.today - timedelta(days=1), cost_usd=7)
        s = openai_billing.balance_summary(self.today)
        self.assertEqual(s['balance'], Decimal('16'))
        self.assertEqual(s['per_day'], Decimal('2'))
        self.assertEqual(s['days_left'], 8)

    def test_low_balance_alert_goes_to_both_addresses_once_a_day(self):
        OpenAICredit.objects.create(amount=10, added_on=self.today - timedelta(days=5))
        OpenAIDailyUsage.objects.create(date=self.today - timedelta(days=1), cost_usd=6)
        now = timezone.now()
        self.assertTrue(openai_billing.check_balance_and_alert(now))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['hello@example.com', 'dev@example.com'])
        self.assertIn('running low', mail.outbox[0].subject)
        self.assertIn('$4.00', mail.outbox[0].body)
        # Not repeated within a day...
        self.assertFalse(openai_billing.check_balance_and_alert(now + timedelta(hours=2)))
        # ...but repeated after a day while still low.
        self.assertTrue(openai_billing.check_balance_and_alert(now + timedelta(hours=25)))

    def test_topping_up_rearms_the_alert(self):
        OpenAICredit.objects.create(amount=10, added_on=self.today - timedelta(days=5))
        OpenAIDailyUsage.objects.create(date=self.today - timedelta(days=1), cost_usd=6)
        now = timezone.now()
        openai_billing.check_balance_and_alert(now)
        OpenAICredit.objects.create(amount=100, added_on=self.today)
        self.assertFalse(openai_billing.check_balance_and_alert(now + timedelta(minutes=5)))
        self.assertIsNone(OpenAIBillingSettings.load().low_alert_sent_at)

    def test_no_alert_without_recorded_credit(self):
        self.assertFalse(openai_billing.check_balance_and_alert())
        self.assertEqual(len(mail.outbox), 0)

    def test_out_of_credit_alert_is_rate_limited(self):
        now = timezone.now()
        self.assertTrue(openai_billing.report_out_of_credit(now))
        self.assertFalse(openai_billing.report_out_of_credit(now + timedelta(hours=1)))
        self.assertIn('run out', mail.outbox[0].subject)

    def test_chat_insufficient_quota_reports_and_says_unavailable(self):
        from .views import AIChatSendMessageView
        body = {'error': {'code': 'insufficient_quota', 'type': 'insufficient_quota', 'message': 'quota'}}
        with override_settings(OPENAI_API_KEY='sk-test'), \
                mock.patch('others.views.requests.post', return_value=FakeResponse(body, 429)), \
                mock.patch('others.tasks.report_openai_out_of_credit.delay') as delay:
            reply, error = AIChatSendMessageView._call_openai([{'role': 'user', 'content': 'hi'}])
        self.assertIsNone(reply)
        self.assertEqual(error.status_code, 503)
        delay.assert_called_once()

    def test_dashboard_shows_balance_for_superuser(self):
        admin_user = get_user_model().objects.create_superuser(email='boss@example.com', password='Pass-1234')
        self.client.force_login(admin_user)
        OpenAICredit.objects.create(amount=25, added_on=timezone.now().date() - timedelta(days=3))
        OpenAIDailyUsage.objects.create(date=timezone.now().date() - timedelta(days=1), cost_usd=Decimal('2.5'),
                                        input_tokens=1200, output_tokens=300, requests=4)
        res = self.client.get('/admin/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'OpenAI credits &amp; usage')
        self.assertContains(res, '$22.50')
        self.assertContains(res, 'data-type="bar"')
        self.assertContains(res, 'data-type="line"')
