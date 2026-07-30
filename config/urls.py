"""Карта адресов экосистемы.

Пути на русском в транслите: их не стыдно показать в адресной строке и
переслать в сообщении.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Экосистема Екатерины Вершанской"
admin.site.site_title = "Экосистема"
admin.site.index_title = "Управление"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('kviz/', include('quiz.urls')),
    path('obuchenie/', include('lms.urls')),
    path('razbor/', include('booking.urls')),
    path('', include('payments.urls')),
    path('profil/', include('users.urls')),
    path('voronka/', include('crm.urls')),
]

# Обложки и аватары в режиме разработки. Видео уроков сюда не попадают —
# они лежат в PROTECTED_MEDIA_ROOT и отдаются только через lms.views.lesson_video.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
