from django.urls import path

from . import views

app_name = 'lms'

urlpatterns = [
    path('kabinet/', views.dashboard, name='dashboard'),
    path('kursy/', views.course_list, name='courses'),
    path('kursy/<slug:slug>/', views.course_detail, name='course'),
    path('kursy/<slug:slug>/urok/<int:pk>/', views.lesson_detail, name='lesson'),
    path('kursy/<slug:slug>/urok/<int:pk>/gotovo/', views.lesson_complete, name='lesson_complete'),
    # Видео отдаётся отдельным адресом с проверкой доступа внутри.
    path('video/<int:pk>/', views.lesson_video, name='lesson_video'),
]
