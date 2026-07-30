"""Короткие выводы по цифрам кабинета.

Работает в двух режимах:

* без ключа Anthropic — наблюдения по правилам. Их немного, но они честные:
  каждое следует из конкретного числа, а не из «ощущения»;
* с ключом — те же цифры уходят в Claude, и он пишет три наблюдения
  человеческим языком.

Правила остаются всегда: если модель недоступна, ключ кончился или запрос
отклонён, кабинет всё равно показывает выводы, а не пустое место.
"""
import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Ответ модели кешируем: перезагрузка страницы не должна стоить денег.
CACHE_TIMEOUT = 60 * 60 * 6

SYSTEM_PROMPT = (
    "Ты — аналитик небольшого онлайн-проекта: психолог продаёт курсы, "
    "личные консультации и подписку на закрытый клуб.\n"
    "Тебе дают цифры за период. Напиши ровно три коротких наблюдения "
    "на русском языке, по одному предложению каждое.\n"
    "Требования: опирайся только на присланные числа и называй их; "
    "не выдумывай данных, которых нет; если цифра нулевая или период пустой — "
    "так и скажи, не притворяйся, что рост есть.\n"
    "Пиши как коллега, а не как отчёт: без канцелярита, без восклицаний, "
    "без слова «рекомендую». Верни только три строки, каждая с новой строки, "
    "без нумерации и маркеров."
)


def rule_based(data):
    """Наблюдения, которые выводятся прямо из чисел.

    Это база, а не заглушка: они показываются и тогда, когда ИИ отключён.
    """
    money, club, funnel, booking = (data['money'], data['club'],
                                    data['funnel'], data['booking'])
    notes = []

    delta = money['delta_percent']
    if money['revenue_30'] == 0:
        notes.append("За последние 30 дней оплат не было.")
    elif delta is None:
        notes.append(f"Выручка за 30 дней — {money['revenue_30']:.0f} ₽, "
                     "сравнивать пока не с чем: месяцем раньше оплат не было.")
    else:
        direction = "больше" if delta >= 0 else "меньше"
        notes.append(f"Выручка за 30 дней — {money['revenue_30']:.0f} ₽, "
                     f"это на {abs(delta)}% {direction}, чем в предыдущие 30 дней.")

    if club['leaving']:
        notes.append(f"{club['leaving']} человек отключили продление — деньги по ним "
                     "уже не придут, хотя доступ ещё открыт.")
    elif club['expiring_week']:
        notes.append(f"На неделе заканчивается оплаченный период у "
                     f"{club['expiring_week']} человек.")
    elif club['active']:
        notes.append(f"В клубе {club['active']} человек, отписок за месяц "
                     f"{club['canceled_30']}.")

    if funnel['attempts'] and funnel['quiz_conversion'] < 50:
        notes.append(f"До результата квиза доходит {funnel['quiz_conversion']}% — "
                     "больше половины бросают на середине.")
    elif funnel['leads']:
        notes.append(f"Из {funnel['leads']} лидов до подписки дошли "
                     f"{funnel['subscribed']}.")

    if booking['canceled_30'] and booking['canceled_30'] >= booking['done_30']:
        notes.append(f"Отменённых разборов за месяц ({booking['canceled_30']}) "
                     f"не меньше, чем проведённых ({booking['done_30']}).")

    return notes[:3]


def _payload(data):
    """Только цифры — без имён, телефонов и прочих персональных данных."""
    money, club, funnel, booking = (data['money'], data['club'],
                                    data['funnel'], data['booking'])
    return {
        'выручка_за_30_дней': round(money['revenue_30']),
        'выручка_за_предыдущие_30_дней': round(money['revenue_prev_30']),
        'оплат_за_30_дней': money['payments_30'],
        'средний_чек': money['average_check'],
        'активных_подписок': club['active'],
        'отключили_продление': club['leaving'],
        'новых_подписок_за_30_дней': club['new_30'],
        'отписок_за_30_дней': club['canceled_30'],
        'начали_квиз': funnel['attempts'],
        'дошли_до_результата': funnel['completed'],
        'всего_лидов': funnel['leads'],
        'оформили_подписку': funnel['subscribed'],
        'разборов_проведено_за_30_дней': booking['done_30'],
        'разборов_отменено_за_30_дней': booking['canceled_30'],
        'предстоящих_разборов': booking['upcoming'],
    }


def ai_enabled():
    return bool(getattr(settings, 'ANTHROPIC_API_KEY', ''))


def ai_insights(data):
    """Просит Claude прокомментировать цифры. None — если не вышло."""
    if not ai_enabled():
        return None

    numbers = _payload(data)
    # Ключ кеша — от самих чисел: пока они не изменились, ответ переиспользуется.
    digest = hashlib.sha256(
        json.dumps(numbers, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache_key = f'insights:{digest}'

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import anthropic
    except ImportError:
        logger.warning("Пакет anthropic не установлен — показываю выводы по правилам.")
        return None

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = client.beta.messages.create(
            model='claude-opus-5',
            max_tokens=1000,
            # Классификаторы модели могут отклонить запрос; fallbacks
            # переигрывает его на запасной модели вместо отказа.
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            output_config={'effort': 'medium'},
            system=SYSTEM_PROMPT,
            messages=[{
                'role': 'user',
                'content': ("Цифры проекта:\n"
                            + json.dumps(numbers, ensure_ascii=False, indent=2)),
            }],
        )
    except anthropic.RateLimitError:
        logger.warning("Claude: превышен лимит запросов.")
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("Claude: ошибка API %s (%s)", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        logger.warning("Claude: не удалось подключиться.")
        return None

    # Проверяем до чтения content: при отказе content пуст или обрезан.
    if response.stop_reason == 'refusal':
        logger.warning("Claude отклонил запрос с цифрами — показываю выводы по правилам.")
        return None

    text = '\n'.join(block.text for block in response.content
                     if getattr(block, 'type', '') == 'text')
    lines = [line.strip(' -•—') for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    lines = lines[:3]
    cache.set(cache_key, lines, CACHE_TIMEOUT)
    return lines


def insights(data):
    """Выводы для кабинета: ИИ, если настроен, иначе правила.

    Вызов ai_insights ровно один: повторный ушёл бы в API второй раз,
    когда первый вернул None.
    """
    from_ai = ai_insights(data)
    return {
        'notes': from_ai or rule_based(data),
        'by_ai': from_ai is not None,
    }
