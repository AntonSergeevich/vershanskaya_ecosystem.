"""Заполняет реквизиты продавца.

Реквизиты ИП — не секрет: они и так публикуются на сайте, требуются в
оферте и лежат в открытом ЕГРИП. Отдельная команда нужна, чтобы не
перебивать девять полей руками в админке и чтобы на новом сервере сайт
поднимался сразу с правильными данными:

    python manage.py seed_requisites

Значения ниже — те, что прислала Екатерина. Если что-то поменяется,
проще поправить в админке (Реквизиты), а не здесь.
"""
from django.core.management.base import BaseCommand

from core.models import LegalInfo

DATA = {
    'entity_type': 'ip',
    'legal_name': 'Индивидуальный предприниматель '
                  'Вершанская Екатерина Федоровна',
    'inn': '245012342898',
    'ogrn': '321246800139300',
    'address': '660020, Россия, Красноярский край, г. Красноярск, '
               'ул. Дмитрия Мартынова, д. 9, кв. 190',
    'bank_account': '40802810200002731604',
    'bank_name': 'АО «ТБанк»',
    'bank_inn': '7710140679',
    'bank_bik': '044525974',
    'bank_corr_account': '30101810145250000974',
    'bank_address': '127287, г. Москва, ул. Хуторская 2-я, д. 38А, стр. 26',
}


def default_of(field_name):
    """Значение поля по умолчанию, каким его задала модель."""
    return LegalInfo._meta.get_field(field_name).get_default()


class Command(BaseCommand):
    help = "Записывает реквизиты продавца в базу."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help="Перезаписать даже заполненные поля.")

    def handle(self, *args, **options):
        info = LegalInfo.load()

        changed = []
        for field, value in DATA.items():
            current = getattr(info, field, '')
            if current == value:
                continue

            # По умолчанию не затираем то, что уже поправили руками в
            # админке: команда запускается повторно при каждой выкатке.
            # «Пустым» считается и значение по умолчанию — иначе форма
            # собственности навсегда осталась бы «самозанятый», ведь
            # пустой она не бывает.
            if options['force'] or not current or current == default_of(field):
                setattr(info, field, value)
                changed.append(field)

        if changed:
            info.save()

        if options['verbosity']:
            if changed:
                self.stdout.write(self.style.SUCCESS(
                    f"Обновлено полей: {len(changed)} ({', '.join(changed)})"))
            else:
                self.stdout.write("Реквизиты уже заполнены, ничего не меняю.")
            if not info.email:
                self.stdout.write(self.style.WARNING(
                    "Не заполнен email для обращений — его требует оферта. "
                    "Добавьте в админке: Реквизиты."))
