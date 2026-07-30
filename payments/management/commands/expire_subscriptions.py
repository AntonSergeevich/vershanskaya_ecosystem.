"""Закрывает доступ по истёкшим подпискам.

Ставится в cron раз в сутки:

    0 3 * * * cd /srv/vershanskaya && python manage.py expire_subscriptions
"""
from django.core.management.base import BaseCommand

from payments.services import expire_subscriptions


class Command(BaseCommand):
    help = "Переводит просроченные подписки в «истекла» и закрывает клуб."

    def handle(self, *args, **options):
        closed = expire_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Закрыто подписок: {closed}."))
