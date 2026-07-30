from django.test import SimpleTestCase

from core.templatetags.ru import counted, emphasis, plural

FORMS = 'урок,урока,уроков'


class PluralTests(SimpleTestCase):
    def test_basic_forms(self):
        cases = {1: 'урок', 2: 'урока', 3: 'урока', 4: 'урока',
                 5: 'уроков', 0: 'уроков', 21: 'урок', 22: 'урока', 25: 'уроков'}
        for number, expected in cases.items():
            with self.subTest(number=number):
                self.assertEqual(plural(number, FORMS), expected)

    def test_teens_are_the_exception(self):
        """11–14 берут форму «уроков», хотя оканчиваются на 1–4."""
        for number in (11, 12, 13, 14, 111, 112):
            with self.subTest(number=number):
                self.assertEqual(plural(number, FORMS), 'уроков')

    def test_non_numeric_falls_back_to_plural(self):
        self.assertEqual(plural(None, FORMS), 'уроков')
        self.assertEqual(plural('много', FORMS), 'уроков')

    def test_counted_prepends_the_number(self):
        self.assertEqual(counted(3, FORMS), '3 урока')
        self.assertEqual(counted(1, FORMS), '1 урок')


class EmphasisTests(SimpleTestCase):
    def test_stars_become_em(self):
        self.assertEqual(emphasis('Понять, *кто вы*'), 'Понять, <em>кто вы</em>')

    def test_html_from_admin_is_escaped(self):
        """Поле редактируется через админку — сырой HTML туда попасть не должен."""
        self.assertEqual(emphasis('<script>alert(1)</script>'),
                         '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_escaping_happens_before_emphasis(self):
        self.assertEqual(emphasis('*<b>x</b>*'), '<em>&lt;b&gt;x&lt;/b&gt;</em>')

    def test_empty_value_is_safe(self):
        self.assertEqual(emphasis(None), '')
