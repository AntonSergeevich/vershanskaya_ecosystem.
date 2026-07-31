"""Превращение прохождения квиза в лид CRM.

Здесь сходятся три вещи: результат квиза, учётная запись человека и его
карточка в воронке. Держим это в одном месте, чтобы вьюха осталась тонкой.
"""
import logging

from crm import services as crm
from core.services import telegram
from users.utils import find_or_create_lead_user

from .models import QuizAttempt

logger = logging.getLogger(__name__)


def latest_result(user):
    """Последнее пройденное прохождение квиза вместе с ответами.

    Нужно там, где о человеке полезно знать заранее: на подтверждении записи
    и в карточке лида. Берём живую попытку, а не копию в момент записи —
    если человек прошёл квиз заново, Екатерина увидит свежий результат.
    """
    if user is None or not getattr(user, 'pk', None):
        return None

    return (QuizAttempt.objects
            .filter(user=user, is_completed=True)
            .select_related('quiz')
            .prefetch_related('answers__question', 'answers__option')
            .order_by('-completed_at')
            .first())


def complete_attempt(attempt, request=None):
    """Считает архетип, создаёт/находит пользователя и двигает лид по воронке.

    Возвращает пользователя, к которому привязана попытка (или None, если
    контактов не оставили — тогда результат просто показывается анонимно).
    """
    archetype = attempt.calculate_result()

    user = attempt.user
    if user is None:
        user = find_or_create_lead_user(
            phone=attempt.contact_phone,
            telegram=attempt.contact_telegram,
            name=attempt.contact_name,
        )
        if user is not None:
            attempt.user = user
            attempt.save(update_fields=['user'])

    if user is None:
        return None

    # Архетип живёт на пользователе: по нему LMS подбирает курсы,
    # а CRM тегирует лида.
    if archetype and user.archetype != archetype:
        user.archetype = archetype
        user.save(update_fields=['archetype'])

    crm.advance_lead(
        user,
        'form_filled',
        note=f"Квиз «{attempt.quiz.title}»: {attempt.result_label or 'без результата'}",
        source=attempt.source or 'Квиз на сайте',
    )

    telegram.notify_admins(
        f"🌟 <b>Новый лид из квиза</b>\n"
        f"{attempt.contact_name or user.display_name}\n"
        f"Архетип: {attempt.result_label or '—'}\n"
        f"Телефон: {attempt.contact_phone or '—'}\n"
        f"Telegram: {'@' + attempt.contact_telegram if attempt.contact_telegram else '—'}"
    )
    logger.info("Квиз завершён: %s → %s", user, archetype)
    return user
