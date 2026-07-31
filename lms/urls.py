from django.urls import path

from . import studio, views

app_name = 'lms'

# Студия курсов — только для сотрудников. Держим выше публичных адресов
# с <slug>, иначе «studiya» перехватился бы как слаг курса.
studio_urls = [
    path('kursy/studiya/', studio.courses, name='studio'),
    path('kursy/studiya/novyy/', studio.course_create, name='studio_course_create'),
    path('kursy/studiya/<int:pk>/', studio.course_edit, name='studio_course'),
    path('kursy/studiya/<int:pk>/udalit/', studio.course_delete, name='studio_course_delete'),

    path('kursy/studiya/<int:pk>/urok/', studio.lesson_create, name='studio_lesson_create'),
    path('kursy/studiya/urok/<int:pk>/', studio.lesson_edit, name='studio_lesson'),
    path('kursy/studiya/urok/<int:pk>/udalit/', studio.lesson_delete, name='studio_lesson_delete'),
    path('kursy/studiya/urok/<int:pk>/<slug:direction>/', studio.lesson_move,
         name='studio_lesson_move'),

    path('kursy/studiya/<int:pk>/razdel/', studio.module_create, name='studio_module_create'),
    path('kursy/studiya/razdel/<int:pk>/', studio.module_edit, name='studio_module'),
    path('kursy/studiya/razdel/<int:pk>/udalit/', studio.module_delete,
         name='studio_module_delete'),
]

urlpatterns = studio_urls + [
    path('kabinet/', views.dashboard, name='dashboard'),
    path('kursy/', views.course_list, name='courses'),
    path('kursy/<slug:slug>/', views.course_detail, name='course'),
    path('kursy/<slug:slug>/urok/<int:pk>/', views.lesson_detail, name='lesson'),
    path('kursy/<slug:slug>/urok/<int:pk>/gotovo/', views.lesson_complete, name='lesson_complete'),
    # Видео отдаётся отдельным адресом с проверкой доступа внутри.
    path('video/<int:pk>/', views.lesson_video, name='lesson_video'),
]
