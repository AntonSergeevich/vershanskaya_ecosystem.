"""Цифры для кабинета Екатерины.

Здесь только подсчёты — никаких выводов «что это значит». Выводы живут
отдельно, в insights.py, чтобы их можно было менять, не трогая арифметику.
"""
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from booking.models import Booking
from crm.models import CRMLead
from payments.models import Payment
from quiz.models import QuizAttempt
from users.models import Subscription

# Екатерина ходит по собственному сайту: проходит квиз, чтобы посмотреть,
# как он выглядит, записывается на тестовый разбор, отмечает оплату руками.
# В цифрах кабинета этого быть не должно — иначе конверсия и выручка врут.
NOT_STAFF = {'user__is_staff': False}


def money_summary(months=12):
    """Выручка по месяцам плюс итоги за последние 30 дней."""
    since = timezone.now() - timedelta(days=31 * months)
    paid = Payment.objects.filter(status=Payment.STATUS_SUCCEEDED, paid_at__gte=since,
                                 **NOT_STAFF)

    by_month = (paid
                .annotate(month=TruncMonth('paid_at'))
                .values('month')
                .annotate(total=Sum('amount'), count=Count('id'))
                .order_by('month'))
    rows = [
        {'month': row['month'], 'total': float(row['total'] or 0), 'count': row['count']}
        for row in by_month
    ]

    month_ago = timezone.now() - timedelta(days=30)
    last_30 = paid.filter(paid_at__gte=month_ago)
    prev_30 = paid.filter(paid_at__gte=month_ago - timedelta(days=30),
                          paid_at__lt=month_ago)

    revenue_now = float(last_30.aggregate(s=Sum('amount'))['s'] or 0)
    revenue_prev = float(prev_30.aggregate(s=Sum('amount'))['s'] or 0)

    return {
        'rows': rows,
        'revenue_30': revenue_now,
        'revenue_prev_30': revenue_prev,
        'delta_percent': percent_change(revenue_prev, revenue_now),
        'payments_30': last_30.count(),
        'average_check': round(revenue_now / last_30.count()) if last_30.count() else 0,
        'total': float(paid.aggregate(s=Sum('amount'))['s'] or 0),
    }


def percent_change(was, became):
    """Прирост в процентах. Рост с нуля процентами не выражается — вернём None."""
    if not was:
        return None
    return round((became - was) / was * 100)


def club_summary():
    """Состояние подписки: сколько людей внутри и сколько уходит."""
    now = timezone.now()
    active = Subscription.objects.filter(status__in=['active', 'canceled'],
                                         next_billing_date__gt=now, **NOT_STAFF)
    month_ago = now - timedelta(days=30)

    canceled_30 = Subscription.objects.filter(status='canceled', **NOT_STAFF,
                                              canceled_at__gte=month_ago).count()
    new_30 = Subscription.objects.filter(start_date__gte=month_ago, **NOT_STAFF).count()

    return {
        'active': active.count(),
        # Отменённые, но ещё действующие — это предупреждение: доход по ним
        # уже не придёт, хотя человек пока внутри.
        'leaving': active.filter(status='canceled').count(),
        'new_30': new_30,
        'canceled_30': canceled_30,
        'expiring_week': active.filter(next_billing_date__lte=now + timedelta(days=7)).count(),
    }


def funnel_summary():
    """Путь от квиза до подписки в абсолютных числах."""
    # exclude по nullable-связи оставляет анонимные попытки (user=None) —
    # это трафик, и он считается. Уходят только свои.
    visible = QuizAttempt.objects.exclude(user__is_staff=True)
    attempts = visible.count()
    completed = visible.filter(is_completed=True).count()
    leads = CRMLead.objects.clients().count()
    subscribed = CRMLead.objects.clients().filter(stage='subscribed').count()

    return {
        'attempts': attempts,
        'completed': completed,
        # Сколько дошло до результата: главный показатель качества квиза.
        'quiz_conversion': round(completed / attempts * 100) if attempts else 0,
        'leads': leads,
        'subscribed': subscribed,
        'lead_to_client': round(subscribed / leads * 100) if leads else 0,
        'stages': list(CRMLead.objects.clients().values('stage')
                                      .annotate(total=Count('id'))),
    }


def booking_summary():
    """Разборы: проведённые, предстоящие, отменённые."""
    now = timezone.now()
    month_ago = now - timedelta(days=30)
    bookings = Booking.objects.filter(created_at__gte=month_ago, **NOT_STAFF)

    return {
        'upcoming': Booking.objects.filter(is_canceled=False, is_completed=False,
                                           slot__start_time__gt=now, **NOT_STAFF).count(),
        'done_30': bookings.filter(is_completed=True).count(),
        'canceled_30': bookings.filter(is_canceled=True).count(),
        'total_30': bookings.count(),
    }


def chart_points(rows, width=680, height=170):
    """Готовит координаты для SVG-графика выручки.

    Считаем на сервере: график рисуется обычным <polyline>, без библиотек
    и без внешних запросов.
    """
    if not rows:
        return {'points': '', 'area': '', 'bars': [], 'max': 0}

    top = max(row['total'] for row in rows) or 1
    step = width / max(len(rows) - 1, 1)

    points = []
    bars = []
    for index, row in enumerate(rows):
        x = index * step
        y = height - (row['total'] / top) * (height - 20)
        points.append(f"{x:.1f},{y:.1f}")
        bars.append({
            'x': x, 'y': y,
            'month': row['month'],
            'total': row['total'],
            'count': row['count'],
        })

    line = ' '.join(points)
    return {
        'points': line,
        # Замкнутый контур под линией — мягкая заливка вместо голого графика.
        'area': f"0,{height} {line} {width},{height}",
        'bars': bars,
        'max': top,
        'width': width,
        'height': height,
    }


def dashboard_data():
    """Всё, что показывает кабинет, одним вызовом."""
    money = money_summary()
    return {
        'money': money,
        'chart': chart_points(money['rows']),
        'club': club_summary(),
        'funnel': funnel_summary(),
        'booking': booking_summary(),
    }
