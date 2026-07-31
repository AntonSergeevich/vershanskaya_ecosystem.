from django.urls import path

from . import views

app_name = 'quiz'

urlpatterns = [
    path('', views.quiz_list, name='list'),
    # Публичная страница архетипа — то, куда ведёт кнопка «поделиться».
    # Ссылку на сам результат отправлять некому: она привязана к сессии.
    path('arhetip/<slug:code>/', views.archetype, name='archetype'),
    path('shag/<int:pk>/', views.question, name='question'),
    # Возврат к уже отвеченному вопросу. Ниже общего адреса шага, чтобы
    # не перехватывать его.
    path('shag/<int:pk>/vopros/<int:order>/', views.question, name='question_at'),
    path('shag/<int:pk>/kontakty/', views.contact, name='contact'),
    path('shag/<int:pk>/rezultat/', views.result, name='result'),
    # Ниже всех: иначе слаг квиза перехватил бы адреса шагов выше.
    path('<slug:slug>/', views.start, name='start'),
]
