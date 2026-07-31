from django import forms

from core.antibot import HumanCheckMixin
from users.utils import normalize_phone, normalize_telegram


class ContactForm(HumanCheckMixin, forms.Form):
    """Последний шаг квиза: контакты в обмен на результат.

    Результат уже посчитан — человек «в одном клике» от ответа, и это самый
    дешёвый момент, чтобы попросить телефон.
    """
    contact_name = forms.CharField(label="Как вас зовут", max_length=120)
    contact_phone = forms.CharField(
        label="Телефон", max_length=20, required=False,
        # Маска включается по data-phone (static/js/phone.js).
        widget=forms.TextInput(attrs={'data-phone': '', 'type': 'tel'}))
    contact_telegram = forms.CharField(label="Telegram", max_length=64, required=False,
                                       help_text="Можно @ник или ссылку — как удобно.")
    consent = forms.BooleanField(label="Согласен на обработку персональных данных")

    def clean_contact_phone(self):
        return normalize_phone(self.cleaned_data.get('contact_phone'))

    def clean_contact_telegram(self):
        return normalize_telegram(self.cleaned_data.get('contact_telegram'))

    def clean(self):
        """Хотя бы один способ связи обязателен — иначе лид бесполезен."""
        cleaned = super().clean()
        phone = cleaned.get('contact_phone')
        telegram = cleaned.get('contact_telegram')
        if not phone and not telegram:
            raise forms.ValidationError("Оставьте телефон или Telegram — иначе не сможем ответить.")
        if phone and len(phone) < 11:
            self.add_error('contact_phone', "Похоже, в номере не хватает цифр.")
        return cleaned
