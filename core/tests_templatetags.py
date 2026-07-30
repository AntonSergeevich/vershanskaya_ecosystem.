from django.test import SimpleTestCase

from core.templatetags.ru import counted, plural

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
