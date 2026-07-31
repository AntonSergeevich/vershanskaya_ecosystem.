"""Общий доступ к рабочим страницам Екатерины (воронка, студия, аналитика).

staff_member_required из Django уводит на форму входа админки — ту самую
«панель программиста», от которой мы кабинет и уводим. Здесь вход обычный,
сайтовый, а посторонним рабочие страницы просто не существуют.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404


def staff_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            # 404, а не 403: посторонним незачем знать, что такая страница есть.
            raise Http404
        return view(request, *args, **kwargs)
    return wrapper
