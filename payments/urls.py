from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('klub/', views.club, name='club'),
    path('oplata/', views.checkout, name='checkout'),
    path('oplata/<uuid:key>/spasibo/', views.success, name='success'),
    path('oplata/<uuid:key>/podtverdit/', views.manual_confirm, name='manual_confirm'),
    path('podpiska/otmena/', views.cancel_subscription, name='cancel_subscription'),
    # Адрес вебхука указывается в личном кабинете эквайринга.
    path('webhook/', views.webhook, name='webhook'),
]
