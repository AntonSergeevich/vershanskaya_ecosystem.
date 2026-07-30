"""Русские склонения для шаблонов.

Встроенный `pluralize` знает только две формы («урок / уроки»), а в русском
их три: 1 урок, 2 урока, 5 уроков. Без этого в интерфейсе появляются
костыли вида «3 урок(ов)».
"""
from django import template

register = template.Library()


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
