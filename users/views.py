from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from crm import services as crm
from lms.models import LessonProgress

from .forms import LoginForm, ProfileForm, RegisterForm


def _safe_next(request, fallback='lms:dashboard'):
    """Куда вернуть человека после входа.

    Проверяем ?next= через url_has_allowed_host_and_scheme, иначе форму входа
    можно было бы использовать как открытый редирект на чужой сайт.
    """
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return reverse(fallback)


def enter(request):
    """Одна страница на вход и регистрацию — так меньше поводов уйти.

    Какая форма отправлена, определяем по полю action: обе живут на одной
    странице, и при ошибке должна «раскрыться» именно та, что заполняли.
    """
    login_form = LoginForm(request=request)
    register_form = RegisterForm()
    active = 'login'

    if request.method == 'POST':
        if request.POST.get('action') == 'register':
            active = 'register'
            register_form = RegisterForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                crm.advance_lead(user, 'new', source='Регистрация на сайте')
                messages.success(request, f"Добро пожаловать, {user.display_name}!")
                return redirect(_safe_next(request))
        else:
            login_form = LoginForm(request=request, data=request.POST)
            if login_form.is_valid():
                login(request, login_form.get_user())
                return redirect(_safe_next(request))

    return render(request, 'users/enter.html', {
        'login_form': login_form,
        'register_form': register_form,
        'active_tab': active,
        'next_url': request.POST.get('next') or request.GET.get('next', ''),
    })


@login_required
def profile(request):
    """Кабинет: личные данные, уровень доступа, подписка и прогресс."""
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён.")
            return redirect('users:profile')
    else:
        form = ProfileForm(instance=request.user)

    recent_progress = (LessonProgress.objects
                       .filter(user=request.user, is_completed=True)
                       .select_related('lesson', 'lesson__course')
                       .order_by('-completed_at')[:8])

    return render(request, 'users/profile.html', {
        'form': form,
        'subscription': request.user.active_subscription,
        'recent_progress': recent_progress,
        'bookings': request.user.bookings.select_related('slot').order_by('-created_at')[:5],
        'attempts': (request.user.quiz_attempts
                     .filter(is_completed=True).select_related('quiz')[:5]),
    })
