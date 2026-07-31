from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = 'users'

# Восстановление пароля — стандартные вьюхи Django с нашими шаблонами.
# Работает только для тех, кто указал email; остальным на странице входа
# предлагается Telegram, где пароля нет вовсе.
password_reset = [
    path('parol/', views.ThrottledPasswordReset.as_view(), name='password_reset'),

    path('parol/otpravleno/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/password_reset_done.html',
    ), name='password_reset_done'),

    path('parol/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='users/password_reset_confirm.html',
        success_url=reverse_lazy('users:password_reset_complete'),
    ), name='password_reset_confirm'),

    path('parol/gotovo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/password_reset_complete.html',
    ), name='password_reset_complete'),
]

urlpatterns = [
    path('vhod/', views.enter, name='enter'),
    path('vhod/telegram/', views.telegram_login, name='telegram_login'),
    path('vyhod/', auth_views.LogoutView.as_view(), name='logout'),
    path('kabinet/', views.profile, name='profile'),
] + password_reset
