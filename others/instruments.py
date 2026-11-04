"""
Validated screening instruments, created (locked) by `setup_assessments`.
Wording, answer values and score ranges follow the published versions and
must not be changed; a change would make scores incomparable with the
validated cut-offs.
"""

PFIZER_NOTICE = (
    'Developed by Drs. Robert L. Spitzer, Janet B.W. Williams, Kurt Kroenke and colleagues, '
    'with an educational grant from Pfizer Inc. No permission required to reproduce, '
    'translate, display or distribute.'
)

TWO_WEEKS = 'Over the last 2 weeks, how often have you been bothered by any of the following problems?'

FREQUENCY_OPTIONS = [
    ('Not at all', 0),
    ('Several days', 1),
    ('More than half the days', 2),
    ('Nearly every day', 3),
]

# Asked after the scored items; part of the form but not scored.
DIFFICULTY_QUESTION = {
    'key': 'difficulty',
    'text': 'If you checked off any problems, how difficult have these problems made it for you '
            'to do your work, take care of things at home, or get along with other people?',
    'question_type': 'single_choice',
    'is_required': False,
    'options': [
        ('Not difficult at all', None),
        ('Somewhat difficult', None),
        ('Very difficult', None),
        ('Extremely difficult', None),
    ],
}


def _items(prefix, texts, safety=None):
    safety = safety or {}
    return [
        {
            'key': f'{prefix}-{n}',
            'text': text,
            'question_type': 'scale',
            'is_required': True,
            'safety_threshold': safety.get(n),
            'options': FREQUENCY_OPTIONS,
        }
        for n, text in enumerate(texts, start=1)
    ]


# Not allowed as a questionnaire key: it's an API path (/api/assessments/trends/).
RESERVED_KEYS = {'trends'}

INSTRUMENTS = [
    {
        'key': 'phq-9',
        'name': 'Mood questionnaire (PHQ-9)',
        'description': '9 questions about the last 2 weeks. Takes about 2 minutes.',
        'instructions': TWO_WEEKS,
        'scoring': 'sum',
        'severity_bands': [
            {'min': 0, 'max': 4, 'label': 'Minimal'},
            {'min': 5, 'max': 9, 'label': 'Mild'},
            {'min': 10, 'max': 14, 'label': 'Moderate'},
            {'min': 15, 'max': 19, 'label': 'Moderately severe'},
            {'min': 20, 'max': 27, 'label': 'Severe'},
        ],
        'frequency_days': 14,
        'copyright_notice': PFIZER_NOTICE,
        'order': 1,
        'questions': _items('phq9', [
            'Little interest or pleasure in doing things',
            'Feeling down, depressed, or hopeless',
            'Trouble falling or staying asleep, or sleeping too much',
            'Feeling tired or having little energy',
            'Poor appetite or overeating',
            'Feeling bad about yourself — or that you are a failure or have let yourself or your family down',
            'Trouble concentrating on things, such as reading the newspaper or watching television',
            'Moving or speaking so slowly that other people could have noticed? Or the opposite — being so '
            'fidgety or restless that you have been moving around a lot more than usual',
            'Thoughts that you would be better off dead or of hurting yourself in some way',
        ], safety={9: 1}) + [DIFFICULTY_QUESTION],
    },
    {
        'key': 'gad-7',
        'name': 'Anxiety questionnaire (GAD-7)',
        'description': '7 questions about the last 2 weeks. Takes about 2 minutes.',
        'instructions': TWO_WEEKS,
        'scoring': 'sum',
        'severity_bands': [
            {'min': 0, 'max': 4, 'label': 'Minimal'},
            {'min': 5, 'max': 9, 'label': 'Mild'},
            {'min': 10, 'max': 14, 'label': 'Moderate'},
            {'min': 15, 'max': 21, 'label': 'Severe'},
        ],
        'frequency_days': 14,
        'copyright_notice': PFIZER_NOTICE,
        'order': 2,
        'questions': _items('gad7', [
            'Feeling nervous, anxious, or on edge',
            'Not being able to stop or control worrying',
            'Worrying too much about different things',
            'Trouble relaxing',
            'Being so restless that it is hard to sit still',
            'Becoming easily annoyed or irritable',
            'Feeling afraid, as if something awful might happen',
        ]) + [DIFFICULTY_QUESTION],
    },
]
