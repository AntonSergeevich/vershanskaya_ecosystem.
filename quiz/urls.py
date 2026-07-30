from django.urls import path

from . import views

app_name = 'quiz'

urlpatterns = [
    path('', views.quiz_list, name='list'),
    path('<slug:slug>/', views.start, name='start'),
    path('shag/<int:pk>/', views.question, name='question'),
    path('shag/<int:pk>/kontakty/', views.contact, name='contact'),
    path('shag/<int:pk>/rezultat/', views.result, name='result'),
]
