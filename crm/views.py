from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from core.services.analytics import dashboard_data
from core.services.insights import ai_enabled, insights
from quiz import services as quiz_services

from . import services
from .models import CRMLead


@staff_required
def analytics(request):
    """Кабинет Екатерины: деньги, клуб, воронка и разборы на одной странице."""
    data = dashboard_data()
    return render(request, 'crm/analytics.html', {
        **data,
        'insights': insights(data),
        'ai_enabled': ai_enabled(),
    })


@staff_required
def board(request):
    """Канбан-доска воронки. Только для сотрудников — здесь видны контакты."""
    return render(request, 'crm/board.html', {
        'columns': services.board_columns(),
        'stats': services.funnel_stats(),
    })


@staff_required
@require_POST
def move_lead(request, pk):
    """Перенос карточки между колонками.

    Отвечает JSON на fetch от drag-and-drop и редиректом на обычную форму —
    доска остаётся рабочей даже без JavaScript.
    """
    lead = get_object_or_404(CRMLead, pk=pk)
    moved = services.set_stage(lead, request.POST.get('stage', ''))

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'moved': moved, 'stage': lead.stage})

    if not moved:
        messages.error(request, "Не удалось перенести карточку.")
    return redirect('crm:board')


@staff_required
def lead_detail(request, pk):
    """Карточка лида: контакты, архетип, история касаний."""
    lead = get_object_or_404(CRMLead.objects.select_related('user'), pk=pk)

    if request.method == 'POST':
        lead.notes = request.POST.get('notes', '').strip()
        lead.save(update_fields=['notes', 'updated_at'])
        messages.success(request, "Заметки сохранены.")
        return redirect('crm:lead', pk=lead.pk)

    user = lead.user
    last_attempt = quiz_services.latest_result(user)
    return render(request, 'crm/lead_detail.html', {
        'lead': lead,
        'attempts': user.quiz_attempts.select_related('quiz')[:5],
        'quiz_answers': last_attempt.answers.all() if last_attempt else None,
        'bookings': user.bookings.select_related('slot')[:5],
        'payments': user.payments.all()[:5],
        'stages': CRMLead.STAGE_CHOICES,
    })
