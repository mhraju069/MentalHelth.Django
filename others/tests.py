from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase

from .models import AssessmentOption, AssessmentQuestion, DailyReport


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


class SeedAssessmentQuestionsTests(APITestCase):
    def test_seeds_default_question_once(self):
        call_command('seed_assessment_questions', stdout=StringIO())
        call_command('seed_assessment_questions', stdout=StringIO())

        question = AssessmentQuestion.objects.get()
        self.assertTrue(question.saves_as_tags)
        self.assertEqual(question.options.count(), 10)
