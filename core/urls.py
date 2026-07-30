from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('dokumenty/rekvizity/', views.requisites, name='requisites'),
    # Ниже общего адреса: иначе slug «rekvizity» перехватил бы страницу выше.
    path('dokumenty/<slug:slug>/', views.legal_page, name='legal'),
]
