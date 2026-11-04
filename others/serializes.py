from rest_framework import serializers
from .models import AssessmentOption, AssessmentQuestion, DailyReport, Feedback, FCMDevice, Notification


class AssessmentOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentOption
        fields = ('id', 'label')


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentQuestion
        fields = ('id', 'text', 'help_text', 'question_type', 'is_required', 'saves_as_tags', 'options')

    def get_options(self, obj):
        # Options are prefetched as active-only by the view.
        return AssessmentOptionSerializer(obj.options.all(), many=True).data


class DailyReportSerializer(serializers.ModelSerializer):
    # Incoming: [{"question_id": "<uuid>", "answer": "text" | ["label", ...]}]
    # Stored:   a snapshot that also carries the question text and type.
    answers = serializers.ListField(child=serializers.DictField(), required=False)

    class Meta:
        model = DailyReport
        exclude = ('created_at', 'updated_at')
        read_only_fields = ('user',)

    def validate_answers(self, value):
        questions = {
            str(q.id): q
            for q in AssessmentQuestion.objects.filter(is_active=True).prefetch_related('options')
        }
        by_question = {}
        for item in value:
            question_id = str(item.get('question_id', ''))
            question = questions.get(question_id)
            if question is None:
                raise serializers.ValidationError('This question is no longer available. Please refresh and try again.')
            by_question[question_id] = (question, item.get('answer'))

        snapshot = []
        for question_id, question in questions.items():
            question, answer = by_question.get(question_id, (question, None))
            answer = self._clean_answer(question, answer)
            if question.is_required and not answer:
                raise serializers.ValidationError(f'Please answer: {question.text}')
            if answer:
                snapshot.append({
                    'question_id': question_id,
                    'question': question.text,
                    'type': question.question_type,
                    'answer': answer,
                })
        return snapshot

    def _validate_ratings(self, attrs):
        if attrs.get('mood_rating') is None:
            # Older app versions send the mood label instead of a rating.
            if not attrs.get('assesment'):
                raise serializers.ValidationError({'mood_rating': 'Please rate your mood.'})
            return

        if attrs.get('anxiety_rating') is None:
            raise serializers.ValidationError({'anxiety_rating': 'Please rate your anxiety.'})

        sleep_hours = attrs.get('sleep_hours')
        if sleep_hours is not None and (sleep_hours * 2) % 1:
            raise serializers.ValidationError({'sleep_hours': 'Use half-hour steps, e.g. 7 or 7.5.'})

        if attrs.get('check_in_type', DailyReport.DETAILED) == DailyReport.DETAILED:
            if sleep_hours is None:
                raise serializers.ValidationError({'sleep_hours': 'Please enter how long you slept.'})
            if not attrs.get('sleep_quality'):
                raise serializers.ValidationError({'sleep_quality': 'Please choose how well you slept.'})

    def _clean_answer(self, question, answer):
        if answer in (None, '', []):
            return None

        if question.question_type == AssessmentQuestion.TEXT:
            if not isinstance(answer, str):
                raise serializers.ValidationError(f'Invalid answer for: {question.text}')
            return answer.strip()[:1000] or None

        labels = answer if isinstance(answer, list) else [answer]
        if not all(isinstance(label, str) for label in labels):
            raise serializers.ValidationError(f'Invalid answer for: {question.text}')
        allowed = {o.label for o in question.options.all() if o.is_active}
        if any(label not in allowed for label in labels):
            raise serializers.ValidationError(f'Invalid option for: {question.text}')
        if question.question_type == AssessmentQuestion.SINGLE_CHOICE:
            if len(labels) > 1:
                raise serializers.ValidationError(f'Choose only one option for: {question.text}')
            return labels[0]
        return list(dict.fromkeys(labels))

    def validate(self, attrs):
        self._validate_ratings(attrs)

        answers = attrs.get('answers')
        # Older app versions send `tags` directly; newer ones send answers
        # and the tags are derived from questions marked "saves as tags".
        if answers:
            tag_questions = set(
                str(pk) for pk in AssessmentQuestion.objects.filter(saves_as_tags=True).values_list('id', flat=True)
            )
            tags = []
            for item in answers:
                if item['question_id'] in tag_questions:
                    values = item['answer'] if isinstance(item['answer'], list) else [item['answer']]
                    tags.extend(v for v in values if v not in tags)
            attrs['tags'] = tags
        return attrs


class FCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMDevice
        fields = ['registration_id', 'device_id']
        read_only_fields = ('user',)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('user',)


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        exclude = ('created_at', 'updated_at')
        read_only_fields = ('user',)
