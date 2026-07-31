"""Формы входа, регистрации и профиля.

Вход по телефону — сознательное решение: почту в этой аудитории помнят хуже,
чем номер, а лид из квиза уже создан именно с телефоном.
"""
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm

from core.antibot import HumanCheckMixin

from .utils import normalize_phone, unique_username

User = get_user_model()


class LoginForm(AuthenticationForm):
    """Логин по телефону, username или email — что человек помнит."""
    username = forms.CharField(label="Телефон, email или логин",
                               widget=forms.TextInput(attrs={'autofocus': True,
                                                             'autocomplete': 'username'}))

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': "Не нашли такую пару логина и пароля. Проверьте раскладку и телефон.",
    }

    def clean(self):
        login = (self.cleaned_data.get('username') or '').strip()
        password = self.cleaned_data.get('password')
        if not (login and password):
            return super().clean()

        self.user_cache = authenticate(self.request, username=login, password=password)
        if self.user_cache is None:
            # Пробуем те же данные как телефон или email — бэкенд по username уже не сработал.
            for candidate in self._alternative_logins(login):
                self.user_cache = authenticate(self.request, username=candidate,
                                               password=password)
                if self.user_cache is not None:
                    break

        if self.user_cache is None:
            raise forms.ValidationError(self.error_messages['invalid_login'],
                                        code='invalid_login',
                                        params={'username': self.username_field.verbose_name})
        self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data

    def _alternative_logins(self, login):
        """username'ы пользователей, у которых совпал телефон или email."""
        lookups = []
        phone = normalize_phone(login)
        if phone:
            lookups.append({'phone': phone})
        if '@' in login:
            lookups.append({'email__iexact': login})

        usernames = []
        for lookup in lookups:
            usernames += list(User.objects.filter(**lookup).values_list('username', flat=True)[:5])
        return usernames


class RegisterForm(HumanCheckMixin, forms.ModelForm):
    """Регистрация по имени и телефону: минимум полей — меньше отвалов."""
    first_name = forms.CharField(label="Как вас зовут", max_length=150)
    # data-phone включает маску «+7 (999) 123-45-67» из static/js/phone.js.
    # Если скрипт не загрузился, сервер всё равно нормализует номер.
    phone = forms.CharField(label="Телефон", max_length=20,
                            widget=forms.TextInput(attrs={'data-phone': '', 'type': 'tel'}),
                            help_text="Понадобится для входа и связи по разбору.")
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput,
                                min_length=6)
    password2 = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name', 'phone', 'email']
        labels = {'email': "Email (необязательно)"}

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data['phone'])
        if len(phone) < 11:
            raise forms.ValidationError("Похоже, в номере не хватает цифр.")
        # Учётка могла быть создана квизом «тихо» — тогда пароль ещё не задан
        # и человек имеет право её присвоить. Обрабатываем это в save().
        self._existing = User.objects.filter(phone=phone).first()
        if self._existing is not None and self._existing.has_usable_password():
            raise forms.ValidationError("Этот номер уже зарегистрирован — попробуйте войти.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') != cleaned.get('password2'):
            self.add_error('password2', "Пароли не совпадают.")
        return cleaned

    def validate_unique(self):
        """Присвоение тихой учётки — не создание второй с тем же телефоном.

        Без этого ModelForm ругался бы на unique-телефон, хотя мы собираемся
        не создать нового пользователя, а дописать пароль существующему.
        """
        if getattr(self, '_existing', None) is not None:
            return
        super().validate_unique()

    def save(self, commit=True):
        """Создаёт пользователя или «присваивает» тихую учётку из квиза."""
        user = getattr(self, '_existing', None) or super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.phone = self.cleaned_data['phone']
        user.email = self.cleaned_data.get('email') or user.email or ''
        if not user.username:
            user.username = unique_username(user.phone)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    """Личные данные в кабинете. Телефон менять нельзя — это логин."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'avatar']
        labels = {
            'first_name': "Имя",
            'last_name': "Фамилия",
            'email': "Email",
            'avatar': "Аватар",
        }
