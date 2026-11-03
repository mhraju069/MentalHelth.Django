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


class SeedAssessmentQuestionsTests(APITestCase):
    def test_seeds_default_question_once(self):
        call_command('seed_assessment_questions', stdout=StringIO())
        call_command('seed_assessment_questions', stdout=StringIO())

        question = AssessmentQuestion.objects.get()
        self.assertTrue(question.saves_as_tags)
        self.assertEqual(question.options.count(), 10)
