from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Course, CourseAccess, Lesson, LessonProgress, Module


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ('order', 'title', 'description')
    show_change_link = True


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ('order', 'module', 'title', 'video_file', 'video_url', 'duration_minutes',
              'is_preview')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'access_level', 'price', 'lesson_count', 'for_archetype',
                    'order', 'is_published', 'created_at']
    list_filter = ['access_level', 'is_published', 'for_archetype', 'created_at']
    list_editable = ['order', 'is_published']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ModuleInline, LessonInline]

    @admin.display(description="Уроков")
    def lesson_count(self, obj):
        return obj.lesson_count


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order']
    list_filter = ['course']
    list_editable = ['order']
    search_fields = ['title']


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'module', 'order', 'has_video_file', 'has_video_url',
                    'is_preview']
    list_filter = ['course', 'is_preview']
    search_fields = ['title', 'content']
    list_editable = ['order', 'is_preview']
    readonly_fields = ['video_player_preview']

    fieldsets = (
        ('Основная информация', {
            'fields': ('course', 'module', 'title', 'order', 'duration_minutes', 'is_preview')
        }),
        ('Видео контент', {
            'fields': ('video_file', 'video_player_preview', 'video_url'),
            'description': 'Загрузите файл с ПК или вставьте внешнюю ссылку. '
                           'Загруженные файлы хранятся вне публичной папки и '
                           'отдаются только тем, у кого есть доступ к курсу.'
        }),
        ('Текстовые материалы', {
            'fields': ('content',),
        }),
    )

    @admin.display(description="Видео на сервере", boolean=True)
    def has_video_file(self, obj):
        return bool(obj.video_file)

    @admin.display(description="Внешняя ссылка", boolean=True)
    def has_video_url(self, obj):
        return bool(obj.video_url)

    @admin.display(description="Превью видео")
    def video_player_preview(self, obj):
        if not obj.pk or not obj.video_file:
            return "Видеофайл не загружен"
        # У защищённого хранилища нет публичного URL — смотрим через ту же
        # вьюху, что и ученики.
        return format_html(
            '<video width="320" height="180" controls style="max-width: 100%; height: auto;">'
            '<source src="{}">'
            'Ваш браузер не поддерживает данный формат видео.'
            '</video>',
            reverse('lms:lesson_video', args=[obj.pk])
        )


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'lesson', 'is_completed', 'started_at', 'completed_at']
    list_filter = ['is_completed', 'lesson__course']
    search_fields = ['user__username', 'user__phone', 'lesson__title']
    autocomplete_fields = ['user', 'lesson']
    readonly_fields = ['started_at', 'completed_at', 'updated_at']


@admin.register(CourseAccess)
class CourseAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'granted_at', 'comment']
    list_filter = ['course']
    search_fields = ['user__username', 'user__phone', 'comment']
    autocomplete_fields = ['user', 'course']
