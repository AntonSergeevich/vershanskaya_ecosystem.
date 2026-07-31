from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from core import antibot
from crm import services as crm
from lms.models import LessonProgress

from . import telegram_auth
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
    register_form = RegisterForm(request=request)
    active = 'login'

    if request.method == 'POST':
        # Ограничение по адресу: регистрация заводит учётки, вход перебирает
        # пароли — и то и другое интересно скриптам, а не людям.
        action = 'registraciya' if request.POST.get('action') == 'register' else 'vhod'
        if antibot.too_many(request, action, limit=20 if action == 'registraciya' else 40):
            messages.error(request, "Слишком много попыток. Попробуйте позже.")
            return redirect('users:enter')

        if request.POST.get('action') == 'register':
            active = 'register'
            register_form = RegisterForm(request.POST, request=request)
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
        # Виджет показываем только когда бот настроен: пустая кнопка,
        # которая ничего не делает, хуже её отсутствия.
        'telegram_bot': settings.TELEGRAM_BOT_USERNAME if settings.TELEGRAM_BOT_TOKEN else '',
    })


def telegram_login(request):
    """Вход через виджет Telegram.

    Виджет присылает данные в адресной строке; их подлинность проверяет
    telegram_auth.authenticate по подписи. Заодно это единственное место,
    где у пользователя появляется telegram_id — без него не отправить ни
    приглашение в клуб, ни уведомление.
    """
    user, created = telegram_auth.authenticate(request.GET.dict())

    if user is None:
        messages.error(request, "Не удалось подтвердить вход через Telegram. "
                                "Попробуйте ещё раз или войдите по телефону.")
        return redirect('users:enter')

    login(request, user)
    if created:
        crm.advance_lead(user, 'new', source='Вход через Telegram')
        messages.success(request, f"Здравствуйте, {user.display_name}! "
                                  "Кабинет создан, пароль не нужен.")
    else:
        messages.success(request, "Telegram привязан — теперь придут приглашение "
                                  "в клуб и уведомления о разборах.")
    return redirect(_safe_next(request))


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


class ThrottledPasswordReset(auth_views.PasswordResetView):
    """Восстановление пароля с ограничением по адресу.

    Форма отправляет письмо на любой введённый адрес. Без ограничения
    через неё можно заваливать чужой ящик письмами с нашего домена — и
    домен быстро окажется в спаме у всех.
    """
    template_name = 'users/password_reset.html'
    email_template_name = 'users/password_reset_email.txt'
    subject_template_name = 'users/password_reset_subject.txt'
    success_url = reverse_lazy('users:password_reset_done')

    def post(self, request, *args, **kwargs):
        if antibot.too_many(request, 'sbros-parolya', limit=10):
            messages.error(request, "Слишком много писем на этот адрес. "
                                    "Попробуйте через час.")
            return redirect('users:password_reset')
        return super().post(request, *args, **kwargs)
