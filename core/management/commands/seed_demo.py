"""Наполняет пустую базу демо-контентом.

Нужен, чтобы после `migrate` сайт был не пустым: есть квиз, курсы, отзывы и
окна для записи — можно сразу прокликать всю воронку.

    python manage.py seed_demo

Команда идемпотентна: повторный запуск ничего не задваивает.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from core.constants import (
    ARCHETYPE_CREATOR,
    ARCHETYPE_HERO,
    ARCHETYPE_LOVER,
    ARCHETYPE_RULER,
    ARCHETYPE_SAGE,
    ARCHETYPE_SEEKER,
)
from core.models import FAQItem, Testimonial
from lms.models import Course, Lesson, Module
from quiz.models import Option, Question, Quiz

QUIZ_SLUG = 'arhetip'

QUESTIONS = [
    ("Что первым выбивает вас из равновесия?",
     "Ответьте про обычную неделю, а не про кризис.",
     [("Ощущение, что живу не свою жизнь", ARCHETYPE_SEEKER),
      ("Невозможность выразить то, что внутри", ARCHETYPE_CREATOR),
      ("Когда решают за меня и без объяснений", ARCHETYPE_SAGE),
      ("Хаос и отсутствие опоры", ARCHETYPE_RULER)]),
    ("Как вы отдыхаете по-настоящему?",
     "",
     [("Меняю обстановку, уезжаю", ARCHETYPE_SEEKER),
      ("Делаю что-то руками", ARCHETYPE_CREATOR),
      ("Читаю и раскладываю мысли", ARCHETYPE_SAGE),
      ("Провожу время с близкими", ARCHETYPE_LOVER)]),
    ("За что вас чаще благодарят?",
     "",
     [("За то, что показал(а) другой взгляд", ARCHETYPE_SEEKER),
      ("За красоту того, что я делаю", ARCHETYPE_CREATOR),
      ("За то, что объяснил(а) сложное просто", ARCHETYPE_SAGE),
      ("За то, что взял(а) ответственность", ARCHETYPE_RULER)]),
    ("Что для вас страшнее?",
     "",
     [("Застрять на одном месте навсегда", ARCHETYPE_SEEKER),
      ("Прожить жизнь, ничего не создав", ARCHETYPE_CREATOR),
      ("Так и не понять, как всё устроено", ARCHETYPE_SAGE),
      ("Остаться без близкого человека", ARCHETYPE_LOVER)]),
    ("Как вы принимаете решения?",
     "",
     [("Пробую и смотрю, что получится", ARCHETYPE_HERO),
      ("Слушаю, как откликается внутри", ARCHETYPE_LOVER),
      ("Собираю информацию и взвешиваю", ARCHETYPE_SAGE),
      ("Смотрю, за что я готов(а) отвечать", ARCHETYPE_RULER)]),
    ("Что вы чаще всего откладываете?",
     "",
     [("Разговор, который всё изменит", ARCHETYPE_LOVER),
      ("Дело, где придётся показать себя", ARCHETYPE_CREATOR),
      ("Решение, где нет гарантий", ARCHETYPE_HERO),
      ("Наведение порядка в делах", ARCHETYPE_RULER)]),
    ("Каким вы хотите быть через год?",
     "",
     [("Свободнее — меньше чужих ожиданий", ARCHETYPE_SEEKER),
      ("Смелее — делать, а не готовиться", ARCHETYPE_HERO),
      ("Точнее — понимать себя без иллюзий", ARCHETYPE_SAGE),
      ("Теплее — ближе к своим людям", ARCHETYPE_LOVER)]),
]

COURSES = [
    {
        'slug': 'pervye-shagi',
        'title': 'Первые шаги: знакомство с архетипами',
        'access_level': 'free',
        'order': 10,
        'description': 'Короткий вводный курс: что такое архетипы, зачем они нужны '
                       'и как заметить свой в обычной жизни.',
        'lessons': [
            ('Зачем вообще архетипы', 12, True),
            ('Шесть фигур внутри нас', 15, True),
            ('Как найти свою ведущую', 18, False),
        ],
    },
    {
        'slug': 'tvorets-praktika',
        'title': 'Творец: практика самовыражения',
        'access_level': 'club',
        'order': 20,
        'for_archetype': ARCHETYPE_CREATOR,
        'description': 'Клубный курс для тех, кто перестал создавать. Разбираем, '
                       'что блокирует, и возвращаем себе право делать.',
        'modules': [
            ('Что мешает', ['Страх чужого взгляда', 'Перфекционизм как защита']),
            ('Что помогает', ['Маленькая ежедневная практика', 'Своё окружение']),
        ],
    },
    {
        'slug': 'glubinnyj-razbor',
        'title': 'Глубинный разбор личной истории',
        'access_level': 'paid',
        'price': 7900,
        'order': 30,
        'description': 'Самостоятельный курс-исследование: восемь занятий, чтобы '
                       'собрать свою историю и увидеть в ней логику.',
        'lessons': [
            ('С чего начинается история', 20, True),
            ('Роли, которые нам достались', 22, False),
            ('Точка, где вы свернули', 25, False),
        ],
    },
]

TESTIMONIALS = [
    ("Марина", "участница клуба, 8 месяцев",
     "Пришла с ощущением «всё нормально, но не моё». Через полгода поменяла работу — "
     "и впервые не жалею."),
    ("Ольга", "прошла личный разбор",
     "За тридцать минут получила больше, чем за год чтения книг по психологии. "
     "Стало видно, где я сама себя останавливаю."),
    ("Ксения", "участница клуба",
     "Ценно, что в чате отвечают по-человечески, а не шаблонами. И что можно "
     "просто послушать, если не готова говорить."),
]

FAQ = [
    ("Что будет после оплаты?",
     "Доступ в кабинет открывается сразу, ссылку в закрытый чат пришлём в Telegram."),
    ("Можно отменить подписку?",
     "Да, в один клик в личном кабинете. Клуб остаётся открытым до конца "
     "оплаченного месяца, деньги за него не сгорают."),
    ("Я ничего не знаю про архетипы. Мне подойдёт?",
     "Да. Начните с бесплатного квиза и вводного курса — этого достаточно, "
     "чтобы понять, ваш это язык или нет."),
    ("Разбор — это терапия?",
     "Нет. Это тридцать минут работы с конкретным запросом. Если увижу, что "
     "нужна терапия, скажу об этом прямо."),
]


class Command(BaseCommand):
    help = "Создаёт демонстрационный контент: квиз, курсы, отзывы, вопросы и слоты."

    def add_arguments(self, parser):
        parser.add_argument('--with-slots', action='store_true',
                            help="Ещё и нагенерить окна для записи на две недели.")

    @transaction.atomic
    def handle(self, *args, **options):
        # verbosity=0 используют тесты — команда не должна засорять их вывод.
        self.quiet = not options['verbosity']
        self._create_quiz()
        self._create_courses()
        self._create_content()

        if options['with_slots']:
            call_command('generate_slots', days=14, verbosity=options['verbosity'])

        self.say(self.style.SUCCESS(
            "Демо-контент готов. Загляните на главную страницу."))

    def say(self, message):
        if not self.quiet:
            self.stdout.write(message)

    def _create_quiz(self):
        quiz, created = Quiz.objects.get_or_create(
            slug=QUIZ_SLUG,
            defaults={
                'title': 'Какой архетип ведёт вас сейчас',
                'intro': 'Семь вопросов о том, как вы живёте на самом деле, а не как '
                         'принято отвечать. Правильных вариантов нет.',
                'outro': 'Архетип — не приговор и не ярлык. Это язык, на котором проще '
                         'говорить о себе.',
            })
        if not created:
            self.say("Квиз уже был — пропускаю.")
            return

        for index, (text, subtitle, options) in enumerate(QUESTIONS, start=1):
            question = Question.objects.create(
                quiz=quiz, text=text, subtitle=subtitle, order=index)
            for position, (option_text, archetype) in enumerate(options, start=1):
                Option.objects.create(question=question, text=option_text,
                                      archetype=archetype, order=position)
        self.say(f"Создан квиз «{quiz.title}» с {len(QUESTIONS)} вопросами.")

    def _create_courses(self):
        for spec in COURSES:
            course, created = Course.objects.get_or_create(
                slug=spec['slug'],
                defaults={
                    'title': spec['title'],
                    'description': spec['description'],
                    'access_level': spec['access_level'],
                    'price': spec.get('price', 0),
                    'order': spec['order'],
                    'for_archetype': spec.get('for_archetype', ''),
                })
            if not created:
                continue

            for order, (title, minutes, preview) in enumerate(spec.get('lessons', []), start=1):
                Lesson.objects.create(course=course, title=title, order=order,
                                      duration_minutes=minutes, is_preview=preview,
                                      content='Материалы урока появятся здесь.')

            order = 0
            for module_order, (module_title, lessons) in enumerate(spec.get('modules', []), start=1):
                module = Module.objects.create(course=course, title=module_title,
                                               order=module_order)
                for lesson_title in lessons:
                    order += 1
                    Lesson.objects.create(course=course, module=module, title=lesson_title,
                                          order=order, duration_minutes=20,
                                          content='Материалы урока появятся здесь.')

            self.say(f"Создан курс «{course.title}».")

    def _create_content(self):
        for order, (author, role, text) in enumerate(TESTIMONIALS, start=1):
            Testimonial.objects.get_or_create(
                author=author, defaults={'role': role, 'text': text, 'order': order})

        for order, (question, answer) in enumerate(FAQ, start=1):
            FAQItem.objects.get_or_create(
                question=question, defaults={'answer': answer, 'order': order})
