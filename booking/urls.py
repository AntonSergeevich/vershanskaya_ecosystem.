from django.urls import path

from . import studio, views

app_name = 'booking'

urlpatterns = [
    path('', views.slots, name='slots'),

    # Расписание Екатерины. Выше адресов с <int:pk>, чтобы «raspisanie»
    # не пытался стать номером окна.
    path('raspisanie/', studio.schedule, name='schedule'),
    path('raspisanie/okno/', studio.slot_add, name='slot_add'),
    path('raspisanie/narezat/', studio.slots_generate, name='slots_generate'),
    path('raspisanie/okno/<int:pk>/skryt/', studio.slot_toggle, name='slot_toggle'),
    path('raspisanie/okno/<int:pk>/udalit/', studio.slot_delete, name='slot_delete'),
    path('raspisanie/den/<slug:day>/', studio.day_toggle, name='day_toggle'),

    path('<int:pk>/zapisatsya/', views.book, name='book'),
    path('zapis/<int:pk>/', views.detail, name='detail'),
    path('zapis/<int:pk>/otmena/', views.cancel, name='cancel'),
]
