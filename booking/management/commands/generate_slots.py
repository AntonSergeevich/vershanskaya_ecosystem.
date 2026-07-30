"""Массовое создание окон под разборы.

Заводить 30-минутные слоты руками — это десятки кликов в админке на каждую
неделю. Команда делает то же самое одной строкой:

    python manage.py generate_slots --days 14 --from 10:00 --to 18:00
"""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from booking.models import BookingSlot


def parse_time(value):
    try:
        hours, minutes = value.split(':')
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError):
        raise CommandError(f"Не понял время «{value}». Формат: 10:00")


class Command(BaseCommand):
    help = "Создаёт слоты для записи на ближайшие дни."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=14,
                            help="На сколько дней вперёд (по умолчанию 14).")
        parser.add_argument('--from', dest='start', default='10:00',
                            help="Начало рабочего дня, например 10:00.")
        parser.add_argument('--to', dest='end', default='18:00',
                            help="Конец рабочего дня, например 18:00.")
        parser.add_argument('--duration', type=int, default=30,
                            help="Длительность окна в минутах (по умолчанию 30).")
        parser.add_argument('--weekdays', default='0,1,2,3,4',
                            help="Дни недели через запятую, 0 — понедельник.")

    def handle(self, *args, **options):
        start_time = parse_time(options['start'])
        end_time = parse_time(options['end'])
        if start_time >= end_time:
            raise CommandError("Начало рабочего дня должно быть раньше конца.")

        duration = timedelta(minutes=options['duration'])
        try:
            weekdays = {int(day) for day in options['weekdays'].split(',') if day.strip()}
        except ValueError:
            raise CommandError("Дни недели задаются числами через запятую, например 0,1,2,3,4")

        today = timezone.localdate()
        created = 0
        skipped = 0

        for offset in range(options['days']):
            day = today + timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue

            cursor = timezone.make_aware(datetime.combine(day, start_time))
            day_end = timezone.make_aware(datetime.combine(day, end_time))

            while cursor + duration <= day_end:
                # Прошедшее время не предлагаем: первый запуск в середине дня
                # не должен наплодить окон «на утро».
                if cursor <= timezone.now():
                    cursor += duration
                    continue

                _, is_new = BookingSlot.objects.get_or_create(
                    start_time=cursor,
                    defaults={'end_time': cursor + duration},
                )
                created += int(is_new)
                skipped += int(not is_new)
                cursor += duration

        self.stdout.write(self.style.SUCCESS(
            f"Создано окон: {created}. Уже существовало: {skipped}."))
