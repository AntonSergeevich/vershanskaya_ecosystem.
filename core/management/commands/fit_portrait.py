"""Готовит портрет под палитру сайта.

Фотографии приходят какие есть: холодный свет студии, синий фон, случайные
пропорции. На кремово-шалфейном сайте такой кадр выглядит вставкой из другого
проекта. Команда приводит его к общему тону — без «улучшайзинга» лица, только
свет, цвет и кадрирование:

    python manage.py fit_portrait ~/foto.jpg --apply

Без --apply файл просто сохраняется рядом, чтобы посмотреть результат.

Чего команда НЕ умеет: убрать цветной фон. Тонировка действует на весь кадр
целиком, поэтому синяя стена станет чуть теплее синей, но не кремовой. Если
фон спорит с сайтом, вариантов два — переснять на нейтральном (белая стена,
бежевая штора, дневной свет из окна) или отдать кадр ретушёру на замену фона.
"""
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageEnhance, ImageOps

from core.models import SiteProfile

# Целевой размер: 4:5 — вертикаль, которая не ломает блок портрета.
TARGET = (1000, 1250)

# Кремовый и шалфейный из палитры сайта (см. static/css/main.css).
CREAM = (250, 247, 242)
SAGE = (140, 155, 126)


def crop_to_ratio(image, ratio=0.8, focus=0.38):
    """Кроп под 4:5.

    Режем не по центру, а ближе к верху (focus): на портретах лицо почти
    всегда выше середины кадра, и центральный кроп срезает макушку.
    """
    width, height = image.size
    target_height = int(width / ratio)

    if target_height <= height:
        top = int((height - target_height) * focus)
        return image.crop((0, top, width, top + target_height))

    target_width = int(height * ratio)
    left = (width - target_width) // 2
    return image.crop((left, 0, left + target_width, height))


def warm_grade(image, strength=0.5):
    """Сдвигает картинку в тёплый кремовый тон.

    strength=0 — оригинал, 1 — совсем «выжженный» бежевый. Половина обычно
    достаточно: холод уходит, кожа остаётся живой.
    """
    # Слегка приглушаем насыщенность: кричащие цвета выбиваются из палитры.
    image = ImageEnhance.Color(image).enhance(1 - 0.25 * strength)

    # Тёплый баланс белого: поднимаем красный канал, опускаем синий.
    red, green, blue = image.split()
    red = red.point(lambda v: min(255, int(v * (1 + 0.06 * strength))))
    blue = blue.point(lambda v: int(v * (1 - 0.08 * strength)))
    image = Image.merge('RGB', (red, green, blue))

    # Кремовая вуаль поверх — то, что связывает фото с фоном страницы.
    veil = Image.new('RGB', image.size, CREAM)
    image = Image.blend(image, veil, 0.10 * strength)

    # Контраст возвращаем, иначе после вуали кадр выглядит выцветшим.
    return ImageEnhance.Contrast(image).enhance(1 + 0.08 * strength)


def soften_edges(image, strength=0.5):
    """Мягко уводит углы в кремовый — портрет «растворяется» в фоне сайта."""
    width, height = image.size
    mask = Image.new('L', (width, height), 0)

    # Радиальный градиент строим через уменьшенный эллипс и размытие:
    # дёшево и без попиксельных циклов.
    from PIL import ImageDraw, ImageFilter
    draw = ImageDraw.Draw(mask)
    inset_x, inset_y = int(width * 0.06), int(height * 0.06)
    draw.ellipse((inset_x, inset_y, width - inset_x, height - inset_y), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=min(width, height) * 0.12))

    veil = Image.new('RGB', (width, height), CREAM)
    faded = Image.composite(image, veil, mask)
    return Image.blend(image, faded, strength)


class Command(BaseCommand):
    help = "Приводит фотографию к палитре сайта и кадрирует под блок портрета."

    def add_arguments(self, parser):
        parser.add_argument('source', help="Путь к исходной фотографии.")
        parser.add_argument('--out', default='', help="Куда сохранить результат.")
        parser.add_argument('--strength', type=float, default=0.5,
                            help="Сила тонировки: 0 — не трогать, 1 — максимум (по умолчанию 0.5).")
        parser.add_argument('--focus', type=float, default=0.38,
                            help="Где резать по вертикали: 0 — от самого верха, 1 — от низа.")
        parser.add_argument('--about', action='store_true',
                            help="Записать во «Второе фото», а не в основной портрет.")
        parser.add_argument('--apply', action='store_true',
                            help="Сразу поставить результат в профиль сайта.")

    def handle(self, *args, **options):
        source = Path(options['source']).expanduser()
        if not source.exists():
            raise CommandError(f"Не нашёл файл: {source}")
        if not 0 <= options['strength'] <= 1:
            raise CommandError("--strength задаётся числом от 0 до 1.")

        with Image.open(source) as raw:
            # exif_transpose: иначе снятое боком фото с телефона ляжет на бок.
            image = ImageOps.exif_transpose(raw).convert('RGB')

        image = crop_to_ratio(image, focus=options['focus'])
        image = image.resize(TARGET, Image.LANCZOS)
        image = warm_grade(image, options['strength'])
        image = soften_edges(image, options['strength'])

        out = Path(options['out']) if options['out'] else \
            source.with_name(f"{source.stem}-site.jpg")
        image.save(out, 'JPEG', quality=92, optimize=True)
        self.stdout.write(self.style.SUCCESS(f"Готово: {out}"))

        if options['apply']:
            profile = SiteProfile.load()
            field = profile.about_photo if options['about'] else profile.portrait
            with open(out, 'rb') as handle:
                field.save(out.name, ContentFile(handle.read()), save=True)
            where = "«Второе фото»" if options['about'] else "«Портрет»"
            self.stdout.write(self.style.SUCCESS(f"Поставлено в профиль сайта → {where}"))
        else:
            self.stdout.write("Посмотрите файл. Понравилось — повторите с --apply.")
