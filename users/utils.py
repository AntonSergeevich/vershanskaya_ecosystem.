"""Утилиты вокруг пользователя: нормализация контактов и «тихая» регистрация."""
import re

from django.contrib.auth import get_user_model


def normalize_phone(raw):
    """Приводит телефон к формату +7XXXXXXXXXX.

    Нужно, чтобы «+7 (999) 123-45-67» и «89991234567» были одним человеком.
    Если номер непохож на российский — возвращаем только цифры с плюсом.
    """
    if not raw:
        return ''
    digits = re.sub(r'\D', '', str(raw))
    if not digits:
        return ''
    if len(digits) == 11 and digits[0] == '8':
        digits = '7' + digits[1:]
    if len(digits) == 10:
        digits = '7' + digits
    return '+' + digits


def normalize_telegram(raw):
    """@Nick, https://t.me/nick, nick → nick (в нижнем регистре)."""
    if not raw:
        return ''
    value = str(raw).strip()
    # Схема необязательна: люди присылают и «t.me/nick», и полную ссылку.
    value = re.sub(r'^(https?://)?(www\.)?(t\.me|telegram\.me)/', '', value,
                   flags=re.IGNORECASE)
    return value.lstrip('@').strip().lower()


def unique_username(base):
    """Свободный username на основе base: phone, phone-2, phone-3…"""
    User = get_user_model()
    base = (base or 'user')[:140]
    candidate = base
    suffix = 2
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def find_or_create_lead_user(phone='', telegram='', name=''):
    """Находит пользователя по контактам или создаёт «тихую» учётку для лида.

    Пароль не задаётся: войти можно только через Telegram или установив
    пароль самостоятельно. Так контакт из квиза сразу попадает в CRM,
    но чужой номер не даёт доступа к аккаунту.
    """
    User = get_user_model()
    phone = normalize_phone(phone)
    telegram = normalize_telegram(telegram)

    if not phone and not telegram:
        return None

    user = None
    if phone:
        user = User.objects.filter(phone=phone).first()
    if user is None and telegram:
        user = User.objects.filter(username__iexact=telegram).first()

    if user is None:
        user = User(
            username=unique_username(phone or telegram),
            phone=phone or None,
            first_name=(name or '')[:150],
        )
        user.set_unusable_password()
        user.save()
    else:
        # Догружаем то, чего не хватало в профиле, ничего не перезатирая.
        updates = []
        if phone and not user.phone:
            user.phone = phone
            updates.append('phone')
        if name and not user.first_name:
            user.first_name = name[:150]
            updates.append('first_name')
        if updates:
            user.save(update_fields=updates)

    return user
