from django.urls import path

from . import views

app_name = 'booking'

urlpatterns = [
    path('', views.slots, name='slots'),
    path('<int:pk>/zapisatsya/', views.book, name='book'),
    path('zapis/<int:pk>/', views.detail, name='detail'),
    path('zapis/<int:pk>/otmena/', views.cancel, name='cancel'),
]
