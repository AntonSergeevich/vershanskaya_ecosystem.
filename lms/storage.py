"""Хранилище для видео уроков.

Файлы кладём вне MEDIA_ROOT, поэтому прямой ссылки на них не существует:
получить видео можно только через lms.views.lesson_video, который сначала
проверяет уровень доступа пользователя.
"""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.signals import setting_changed
from django.utils.functional import cached_property


class ProtectedStorage(FileSystemStorage):
    """FileSystemStorage, читающий корень из PROTECTED_MEDIA_ROOT.

    Родительский класс умеет подхватывать только MEDIA_ROOT, поэтому путь и
    сброс кеша при смене настройки описываем сами — иначе override_settings
    в тестах молча писал бы файлы в боевой каталог.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setting_changed.connect(self._clear_protected_location)

    @cached_property
    def base_location(self):
        return self._value_or_setting(self._location, settings.PROTECTED_MEDIA_ROOT)

    def _clear_protected_location(self, setting, **kwargs):
        if setting == 'PROTECTED_MEDIA_ROOT':
            self.__dict__.pop('base_location', None)
            self.__dict__.pop('location', None)


# base_url не задаём намеренно: обращение к .url() упадёт с ValueError,
# и никто случайно не сошлётся на файл в обход проверки доступа.
_storage = ProtectedStorage()


def protected_storage():
    """Callable, а не готовый объект: так в миграцию попадает ссылка на
    функцию, а не путь конкретной машины."""
    return _storage
