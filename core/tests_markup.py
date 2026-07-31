"""Разметка текстов курсов и уроков."""
from django.test import TestCase

from core.services.markup import plain, render


class MarkupTests(TestCase):
    def test_paragraphs_are_split_by_an_empty_line(self):
        """Перенос строки — не новый абзац: в textarea его жмут просто так."""
        html = render("Первая строка\nвторая строка\n\nНовый абзац")
        self.assertEqual(html, "<p>Первая строка вторая строка</p>\n<p>Новый абзац</p>")

    def test_bold_and_italic(self):
        self.assertIn('<strong>важно</strong>', render('Это **важно**'))
        self.assertIn('<em>тонко</em>', render('Это *тонко*'))

    def test_bold_wins_over_italic(self):
        """Иначе одна звёздочка съедает половину **жирного**."""
        self.assertEqual(render('**оба**'), '<p><strong>оба</strong></p>')

    def test_headings_lists_and_quote(self):
        html = render("## Заголовок\n\n- раз\n- два\n\n1. первый\n\n> Мысль")
        self.assertIn('<h2>Заголовок</h2>', html)
        self.assertIn('<ul>\n<li>раз</li>\n<li>два</li>\n</ul>', html)
        self.assertIn('<ol>\n<li>первый</li>\n</ol>', html)
        self.assertIn('<blockquote>Мысль</blockquote>', html)

    def test_quote_survives_escaping(self):
        """Цитату ищем в исходном тексте: после escape там было бы «&gt;»."""
        self.assertIn('<blockquote>', render('> цитата'))

    def test_links_open_in_a_new_tab(self):
        html = render('[канал](https://t.me/kanal)')
        self.assertIn('<a href="https://t.me/kanal" target="_blank" rel="noopener">канал</a>',
                      html)

    def test_a_script_cannot_be_smuggled_in(self):
        """Главное свойство: в базе текст, теги ставим только мы."""
        html = render('<script>alert(1)</script>\n\n<b onclick="x">жирный</b>')
        # Всё чужое осталось текстом: угловых скобок в разметке нет, есть
        # только их безопасная запись.
        self.assertNotIn('<script', html)
        self.assertNotIn('<b ', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;b onclick=&quot;x&quot;&gt;', html)

    def test_javascript_links_are_not_links(self):
        """[клик](javascript:...) стал бы рабочей ссылкой на чужой код."""
        html = render('[клик](javascript:alert(1))')
        # Ссылка не собралась вовсе — адрес остался видимым текстом.
        self.assertNotIn('<a ', html)
        self.assertIn('[клик](javascript:alert(1))', html)

    def test_ampersand_in_a_link_stays_valid(self):
        html = render('[поиск](https://ya.ru/?a=1&b=2)')
        self.assertIn('href="https://ya.ru/?a=1&amp;b=2"', html)

    def test_empty_text_renders_to_nothing(self):
        self.assertEqual(render(''), '')
        self.assertEqual(render(None), '')

    def test_plain_strips_the_markers(self):
        """В карточках-превью текст обрезается — звёздочки бы там и торчали."""
        self.assertEqual(plain('## Начало\n**Жирный** и [ссылка](https://ok.ru)'),
                         'Начало\nЖирный и ссылка')
