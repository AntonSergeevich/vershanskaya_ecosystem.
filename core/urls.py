from django.contrib.sitemaps.views import sitemap
from django.urls import path

from . import views
from .sitemaps import SITEMAPS

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),

    # Для поисковиков. Вне пространства имён core: адреса /robots.txt и
    # /sitemap.xml ищут именно в корне и ровно с такими именами.
    path('robots.txt', views.robots, name='robots'),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='sitemap'),
    path('dokumenty/rekvizity/', views.requisites, name='requisites'),
    # Ниже общего адреса: иначе slug «rekvizity» перехватил бы страницу выше.
    path('dokumenty/<slug:slug>/', views.legal_page, name='legal'),
]
