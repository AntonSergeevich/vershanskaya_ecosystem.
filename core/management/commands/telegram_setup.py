"""Помогает привязать Telegram-бота: показывает, какой chat_id куда вписать.

Порядок:

1. Создайте бота у @BotFather, получите токен, впишите в .env:
   TELEGRAM_BOT_TOKEN=...
2. Напишите своему боту любое сообщение (например «привет»).
   Если нужны уведомления в групповой чат — добавьте бота в группу
   и напишите там.
3. Запустите:  python manage.py telegram_setup

Команда покажет chat_id всех, кто недавно писал боту, — останется
скопировать нужный в TELEGRAM_ADMIN_CHAT_ID (личные уведомления)
или TELEGRAM_CLUB_CHAT_ID (закрытый чат клуба).
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services import telegram


class Command(BaseCommand):
    help = "Показывает chat_id для настройки уведомлений в Telegram."

    def add_arguments(self, parser):
        parser.add_argument('--test', action='store_true',
                            help="Отправить тестовое сообщение на текущий TELEGRAM_ADMIN_CHAT_ID.")

    def handle(self, *args, **options):
        if not telegram.is_configured():
            raise CommandError(
                "TELEGRAM_BOT_TOKEN не задан. Получите токен у @BotFather "
                "и впишите его в .env, затем повторите."
            )

        if options['test']:
            return self.send_test()

        updates = telegram._call('getUpdates', {'limit': 20})
        if updates is None:
            raise CommandError("Telegram не ответил. Проверьте токен и доступ в сеть.")
        if not updates:
            raise CommandError(
                "Боту никто не писал. Напишите ему любое сообщение "
                "(и добавьте в групповой чат, если нужны уведомления туда), "
                "затем запустите команду снова."
            )

        seen = {}
        for update in updates:
            message = update.get('message') or update.get('channel_post') or {}
            chat = message.get('chat') or {}
            if chat.get('id') is not None:
                seen[chat['id']] = chat

        self.stdout.write(self.style.SUCCESS("Нашёл такие чаты:\n"))
        for chat_id, chat in seen.items():
            kind = chat.get('type', '?')
            title = chat.get('title') or ' '.join(
                filter(None, [chat.get('first_name'), chat.get('last_name')])) or '—'
            hint = ("→ в TELEGRAM_ADMIN_CHAT_ID" if kind == 'private'
                    else "→ в TELEGRAM_CLUB_CHAT_ID")
            self.stdout.write(f"  {chat_id}   {kind:10} {title}   {hint}")

        self.stdout.write(
            "\nВпишите нужный id в .env, перезапустите приложение и проверьте:\n"
            "  python manage.py telegram_setup --test")

    def send_test(self):
        if not settings.TELEGRAM_ADMIN_CHAT_ID:
            raise CommandError("TELEGRAM_ADMIN_CHAT_ID пуст — сначала заполните его в .env.")

        result = telegram.notify_admins(
            "🌿 Проверка связи. Если вы это читаете, уведомления настроены:\n"
            "будут приходить записи на разбор, оплаты и отмены подписки."
        )
        if result is None:
            raise CommandError(
                "Сообщение не ушло. Частая причина — бот не может писать первым: "
                "напишите ему сами хотя бы один раз."
            )
        self.stdout.write(self.style.SUCCESS("Отправлено. Проверьте Telegram."))
