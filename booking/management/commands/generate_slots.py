"""Массовое создание окон под разборы.

То же самое можно сделать кнопкой в расписании кабинета — команда осталась
для первого запуска на сервере и для cron, который раз в неделю открывает
следующую:

    python manage.py generate_slots --days 14 --from 10:00 --to 18:00
"""
from datetime import time

from django.core.management.base import BaseCommand, CommandError

from booking.services import generate_slots


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
        parser.add_argument('--weekdays', default='0,1,2,3,4,5,6',
                            help="Дни недели через запятую, 0 — понедельник. "
                                 "По умолчанию все семь.")

    def handle(self, *args, **options):
        try:
            weekdays = {int(day) for day in options['weekdays'].split(',') if day.strip()}
        except ValueError:
            raise CommandError("Дни недели задаются числами через запятую, например 0,1,2,3,4")

        try:
            created, existed = generate_slots(
                days=options['days'],
                start_time=parse_time(options['start']),
                end_time=parse_time(options['end']),
                duration=options['duration'],
                weekdays=weekdays,
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        if options['verbosity']:
            self.stdout.write(self.style.SUCCESS(
                f"Создано окон: {created}. Уже существовало: {existed}."))
