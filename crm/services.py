"""Автоматизация воронки: лид сам двигается по канбану от действий клиента.

Правило одно: этап можно только продвинуть вперёд. Если менеджер вручную
поставил «Разбор проведён», автоматика от заполненной анкеты не откатит его назад.
"""
import logging

from django.db.models import Count
from django.utils import timezone

from core.services import telegram

from .models import CRMLead

logger = logging.getLogger(__name__)

# Порядок этапов воронки — индекс задаёт «вперёд» и «назад».
STAGE_ORDER = ['new', 'form_filled', 'slot_booked', 'session_done', 'subscribed']


def stage_index(stage):
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        # closed_lost и любые будущие этапы вне линейной воронки.
        return -1


def get_or_create_lead(user, source=''):
    """Возвращает лид пользователя, создавая его при первом касании.

    Для сотрудников лид не заводим вовсе: Екатерина ходит по собственному
    сайту и её собственные шаги не должны попадать в воронку.
    """
    if user.is_staff:
        return None

    lead, created = CRMLead.objects.get_or_create(
        user=user,
        defaults={'source': source or 'Сайт'},
    )
    if created:
        logger.info("CRM: создан лид для %s (источник: %s)", user, lead.source)
    return lead


def advance_lead(user, stage, note='', source=''):
    """Двигает лид на указанный этап, если это шаг вперёд.

    Возвращает лид или None — если пользователя нет (аноним) либо это
    сотрудник, которому в воронке не место.
    """
    if user is None or not getattr(user, 'pk', None):
        return None

    lead = get_or_create_lead(user, source=source)
    if lead is None:
        return None

    if stage_index(stage) > stage_index(lead.stage):
        lead.stage = stage
        lead.save(update_fields=['stage', 'updated_at'])
        logger.info("CRM: лид %s переведён на этап «%s»", user, lead.get_stage_display())

    if note:
        lead.notes = f"{lead.notes}\n{note}".strip() if lead.notes else note
        lead.save(update_fields=['notes', 'updated_at'])

    return lead


def set_stage(lead, stage):
    """Ручной перенос карточки в канбане — здесь можно и назад.

    Автоматика ходит только вперёд (advance_lead), а человек видит контекст
    целиком и вправе вернуть лида на предыдущий этап или закрыть его.
    """
    valid = {code for code, _ in CRMLead.STAGE_CHOICES}
    if stage not in valid or lead.stage == stage:
        return False
    lead.stage = stage
    lead.save(update_fields=['stage', 'updated_at'])
    logger.info("CRM: лид %s вручную переведён на «%s»", lead.user, lead.get_stage_display())
    return True


def board_columns():
    """Данные для канбан-доски: колонки в порядке воронки с лидами внутри."""
    leads = (CRMLead.objects.clients()
             .select_related('user')
             .order_by('-updated_at'))

    grouped = {code: [] for code, _ in CRMLead.STAGE_CHOICES}
    for lead in leads:
        grouped.setdefault(lead.stage, []).append(lead)

    return [
        {'code': code, 'title': title, 'leads': grouped.get(code, [])}
        for code, title in CRMLead.STAGE_CHOICES
    ]


def funnel_stats():
    """Сколько лидов на каждом этапе и какая конверсия дошла до подписки."""
    counts = {code: 0 for code, _ in CRMLead.STAGE_CHOICES}
    for row in CRMLead.objects.clients().values('stage').annotate(total=Count('id')):
        counts[row['stage']] = row['total']

    total = sum(counts.values()) or 1
    return {
        'counts': counts,
        'total': sum(counts.values()),
        'rows': [
            {'code': code, 'title': title, 'count': counts.get(code, 0),
             'percent': round(counts.get(code, 0) / total * 100)}
            for code, title in CRMLead.STAGE_CHOICES
        ],
        'conversion': round(counts.get('subscribed', 0) / total * 100, 1),
    }


def send_campaign(campaign):
    """Рассылает сообщение кампании лидам нужного этапа.

    Пишем только тем, у кого есть Telegram ID: слать «в никуда» бессмысленно,
    а SMS-шлюз в проекте пока не подключён.
    """
    leads = CRMLead.objects.clients().select_related('user')
    if campaign.target_stage:
        leads = leads.filter(stage=campaign.target_stage)

    sent = 0
    for lead in leads:
        if not lead.user.telegram_id:
            continue
        telegram.send_message(lead.user.telegram_id, campaign.message_text)
        sent += 1

    campaign.is_sent = True
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=['is_sent', 'sent_at'])
    logger.info("CRM: рассылка «%s» отправлена %s получателям", campaign.title, sent)
    return sent
