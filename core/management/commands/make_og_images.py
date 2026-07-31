"""Картинки для ссылок в мессенджерах (Open Graph).

Когда ссылку на сайт бросают в чат, Telegram и WhatsApp показывают
превью: заголовок, описание и картинку. Без картинки ссылка выглядит
как строчка текста, и по ней не кликают.

Картинки собираются заранее и лежат в static — на запросе ничего не
рисуется. Запускать надо только когда поменялись тексты архетипов:

    python manage.py make_og_images
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.constants import ARCHETYPE_CHOICES, ARCHETYPE_DESCRIPTIONS

WIDTH, HEIGHT = 1200, 630

# Палитра сайта — превью должно узнаваться как его продолжение.
CREAM = (250, 247, 242)
SAND = (242, 236, 226)
SAGE = (140, 155, 126)
SAGE_DEEP = (109, 124, 96)
CLAY = (196, 131, 106)
INK = (58, 54, 50)
INK_SOFT = (106, 99, 92)

# DejaVu есть почти в любом Linux и знает кириллицу; Liberation — запасной.
FONT_DIRS = [
    Path('/usr/share/fonts/truetype/dejavu'),
    Path('/usr/share/fonts/truetype/liberation'),
]
SERIF = ['DejaVuSerif.ttf', 'LiberationSerif-Regular.ttf']
SERIF_BOLD = ['DejaVuSerif-Bold.ttf', 'LiberationSerif-Bold.ttf']
SANS = ['DejaVuSans.ttf', 'LiberationSans-Regular.ttf']


class Command(BaseCommand):
    help = "Рисует картинки-превью для ссылок (Open Graph)"

    def handle(self, *args, **options):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            raise SystemExit("Нужна библиотека Pillow: pip install Pillow")

        self.Image, self.ImageDraw, self.ImageFont = Image, ImageDraw, ImageFont

        target = Path(settings.BASE_DIR) / 'static' / 'img' / 'og'
        target.mkdir(parents=True, exist_ok=True)

        made = [self.draw(
            target / 'default.png',
            eyebrow="Екатерина Вершанская · психолог",
            title="Понять, кто вы,\nи перестать жить\nчужую жизнь",
            note="Семь вопросов — и станет видно, какой архетип ведёт вас сейчас",
            title_size=70,
        )]

        for code, label in ARCHETYPE_CHOICES:
            made.append(self.draw(
                target / f'{code}.png',
                eyebrow="Мой архетип",
                title=label,
                note=ARCHETYPE_DESCRIPTIONS.get(code, ''),
                title_size=118,
            ))

        if options['verbosity']:
            self.stdout.write(self.style.SUCCESS(
                f"Готово: {len(made)} картинок в {target}"))

    # --- Рисование ---------------------------------------------------------

    def font(self, names, size):
        for directory in FONT_DIRS:
            for name in names:
                path = directory / name
                if path.exists():
                    return self.ImageFont.truetype(str(path), size)
        # Без шрифта с кириллицей текст был бы набором квадратов — лучше
        # сказать об этом прямо, чем выложить такую картинку в мессенджеры.
        raise SystemExit("Не нашёл шрифт с кириллицей (DejaVu или Liberation). "
                         "Установите пакет fonts-dejavu.")

    def draw(self, path, eyebrow, title, note, title_size):
        image = self.Image.new('RGB', (WIDTH, HEIGHT), CREAM)
        canvas = self.ImageDraw.Draw(image)

        # Мягкое пятно в углу — то же, что на сайте делает .blob-bg.
        canvas.ellipse([WIDTH - 380, -220, WIDTH + 200, 360], fill=SAND)
        canvas.ellipse([-160, HEIGHT - 220, 260, HEIGHT + 200], fill=SAND)

        margin = 88
        canvas.text((margin, 92), eyebrow.upper(),
                    font=self.font(SANS, 24), fill=CLAY)

        y = 150
        title_font = self.font(SERIF_BOLD, title_size)
        for line in title.split('\n'):
            canvas.text((margin, y), line, font=title_font, fill=INK)
            y += int(title_size * 1.22)

        y += 18
        note_font = self.font(SANS, 30)
        for line in wrap(note, note_font, WIDTH - margin * 2 - 60, canvas):
            canvas.text((margin, y), line, font=note_font, fill=INK_SOFT)
            y += 44

        # Подпись внизу: у кого спрашивать, если картинку переслали дальше.
        canvas.line([margin, HEIGHT - 96, margin + 54, HEIGHT - 96], fill=SAGE, width=3)
        canvas.text((margin, HEIGHT - 78), "Екатерина Вершанская · архетипы и разборы",
                    font=self.font(SANS, 26), fill=SAGE_DEEP)

        image.save(path, 'PNG', optimize=True)
        return path


def wrap(text, font, max_width, canvas):
    """Разбивает строку по ширине картинки — переносов в PIL нет."""
    words = (text or '').split()
    lines, current = [], ''
    for word in words:
        candidate = f"{current} {word}".strip()
        if canvas.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
