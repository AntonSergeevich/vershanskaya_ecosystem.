"""Простое форматирование текста для курсов и уроков.

Полноценный визуальный редактор пришлось бы либо тащить с чужого CDN, либо
писать самому — и в обоих случаях он отдаёт в базу готовый HTML, который
дальше надо чистить, иначе через поле «Описание» на сайт въезжает чужой
скрипт. Здесь наоборот: в базе лежит обычный текст с пометками, а HTML
собираем мы — вставить свой тег через него нельзя в принципе.

Что понимает:
    ## Заголовок
    **жирный**  *курсив*
    - список          1. нумерованный список
    > цитата
    [текст](https://ссылка)
    пустая строка — новый абзац
"""
import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

# Порядок важен: жирный ищем до курсива, иначе ** съест одна звёздочка.
INLINE = [
    (re.compile(r'\*\*(.+?)\*\*'), r'<strong>\1</strong>'),
    (re.compile(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])'), r'<em>\1</em>'),
]

# Ссылки: адрес пропускаем только http(s) и mailto. Без этой проверки
# [клик](javascript:...) стал бы рабочей ссылкой на чужой код.
LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+|mailto:[^\s)]+)\)')

HEADING = re.compile(r'^(#{2,3})\s+(.*)$')
BULLET = re.compile(r'^[-*]\s+(.*)$')
NUMBER = re.compile(r'^\d+[.)]\s+(.*)$')
QUOTE = re.compile(r'^>\s?(.*)$')


def inline(text):
    """Разметка внутри строки.

    Экранируем здесь, а не в самом начале: разбор строк идёт по исходному
    тексту, где цитата начинается с «>», а не с «&gt;». Экранирование всё
    равно происходит раньше, чем в строку попадает хоть один наш тег.
    """
    text = escape(text)
    text = LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    for pattern, replacement in INLINE:
        text = pattern.sub(replacement, text)
    return text


def render(text):
    """Текст с пометками → безопасный HTML."""
    if not text:
        return mark_safe('')

    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    html = []
    paragraph = []
    list_tag = None

    def close_paragraph():
        if paragraph:
            # Соседние строки склеиваем в один абзац: в текстовом поле люди
            # переносят строку, чтобы не тянуть её до края, а не чтобы
            # начать новую мысль. Новый абзац — это пустая строка.
            html.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_tag
        if list_tag:
            html.append(f"</{list_tag}>")
            list_tag = None

    def open_list(tag):
        nonlocal list_tag
        if list_tag != tag:
            close_list()
            html.append(f"<{tag}>")
            list_tag = tag

    for line in lines:
        stripped = line.strip()

        if not stripped:
            close_paragraph()
            close_list()
            continue

        heading = HEADING.match(stripped)
        if heading:
            close_paragraph()
            close_list()
            level = len(heading.group(1))
            html.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            continue

        bullet = BULLET.match(stripped)
        if bullet:
            close_paragraph()
            open_list('ul')
            html.append(f"<li>{inline(bullet.group(1))}</li>")
            continue

        number = NUMBER.match(stripped)
        if number:
            close_paragraph()
            open_list('ol')
            html.append(f"<li>{inline(number.group(1))}</li>")
            continue

        quote = QUOTE.match(stripped)
        if quote:
            close_paragraph()
            close_list()
            html.append(f"<blockquote>{inline(quote.group(1))}</blockquote>")
            continue

        close_list()
        paragraph.append(stripped)

    close_paragraph()
    close_list()
    return mark_safe('\n'.join(html))


MARKERS = re.compile(r'\*{1,2}|^\s*(?:[-*]|\d+[.)]|>|#{2,3})\s+', re.MULTILINE)


def plain(text):
    """Текст без пометок — для превью в карточках и meta-описаний."""
    without_links = LINK.sub(r'\1', text or '')
    return MARKERS.sub('', without_links).strip()
