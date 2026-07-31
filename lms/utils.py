"""Вспомогательное для студии курсов."""
from django.utils.text import slugify

# Транслитерация нужна потому, что django.utils.text.slugify выбрасывает
# кириллицу целиком: «Первые шаги» превратились бы в пустую строку, а слаг
# участвует в адресе курса и обязан быть уникальным и непустым.
RU_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def slugify_ru(text):
    """Слаг из русского названия: «Путь Творца» → «put-tvortsa»."""
    latin = ''.join(RU_TO_LAT.get(char, char) for char in (text or '').lower())
    return slugify(latin)


def unique_slug(model, text, exclude_pk=None):
    """Свободный слаг: к занятому дописываем -2, -3 и так далее.

    Екатерина название не проверяет на уникальность и не обязана: два курса
    вполне могут называться похоже, а падать с ошибкой базы на сохранении
    формы — плохой способ об этом сообщить.
    """
    base = slugify_ru(text) or 'kurs'
    candidate, counter = base, 1
    while True:
        taken = model.objects.filter(slug=candidate)
        if exclude_pk is not None:
            taken = taken.exclude(pk=exclude_pk)
        if not taken.exists():
            return candidate
        counter += 1
        candidate = f"{base}-{counter}"
