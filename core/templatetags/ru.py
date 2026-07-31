"""Русские склонения для шаблонов.

Встроенный `pluralize` знает только две формы («урок / уроки»), а в русском
их три: 1 урок, 2 урока, 5 уроков. Без этого в интерфейсе появляются
костыли вида «3 урок(ов)».
"""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

EMPHASIS = re.compile(r'\*([^*]+)\*')


@register.filter
def emphasis(text):
    """*Слово* → <em>Слово</em>.

    Нужно, чтобы Екатерина могла выделить часть заголовка из админки и при
    этом не могла случайно (или намеренно) вставить в страницу HTML:
    экранируем всё, а теги добавляем сами.
    """
    return mark_safe(EMPHASIS.sub(r'<em>\1</em>', escape(text or '')))


@register.filter
def plural(count, forms):
    """{{ n|plural:"урок,урока,уроков" }} → правильная форма слова.

    Формы перечисляются в порядке: для 1, для 2–4, для 5 и больше.
    """
    variants = [form.strip() for form in str(forms).split(',')]
    if len(variants) != 3:
        return variants[-1] if variants else ''

    try:
        number = abs(int(count))
    except (TypeError, ValueError):
        return variants[2]

    # 11–14 — исключение: «одиннадцать уроков», а не «одиннадцать урок».
    if number % 100 in range(11, 15):
        return variants[2]
    remainder = number % 10
    if remainder == 1:
        return variants[0]
    if remainder in (2, 3, 4):
        return variants[1]
    return variants[2]


@register.filter
def counted(count, forms):
    """Число вместе со словом: {{ n|counted:"урок,урока,уроков" }} → «3 урока»."""
    return f"{count} {plural(count, forms)}"


@register.filter
def rich(text):
    """Текст с простой разметкой → HTML. Смотрите core.services.markup."""
    from core.services.markup import render
    return render(text)


@register.filter
def plain(text):
    """Тот же текст, но без пометок форматирования — для коротких превью."""
    from core.services.markup import plain as strip_markup
    return strip_markup(text)
