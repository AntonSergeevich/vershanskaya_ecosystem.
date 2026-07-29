from django.contrib import admin
from django.utils.html import format_html
from .models import Course, Lesson


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ('order', 'title', 'video_file', 'video_url', 'is_preview')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'access_level', 'price', 'is_published', 'created_at']
    list_filter = ['access_level', 'is_published', 'created_at']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonInline]
    ordering = ['-created_at']


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'has_video_file', 'has_video_url', 'is_preview']
    list_filter = ['course', 'is_preview']
    search_fields = ['title', 'content']
    list_editable = ['order', 'is_preview']
    readonly_fields = ['video_player_preview']

    fieldsets = (
        ('Основная информация', {
            'fields': ('course', 'title', 'order', 'is_preview')
        }),
        ('Видео контент', {
            'fields': ('video_file', 'video_player_preview', 'video_url'),
            'description': 'Загрузите файл с ПК или вставьте внешнюю ссылку.'
        }),
        ('Текстовые материалы', {
            'fields': ('content',),
        }),
    )

    @admin.display(description="Видео на сервере")
    def has_video_file(self, obj):
        return bool(obj.video_file)
    has_video_file.boolean = True

    @admin.display(description="Внешняя ссылка")
    def has_video_url(self, obj):
        return bool(obj.video_url)
    has_video_url.boolean = True

    @admin.display(description="Превью видео")
    def video_player_preview(self, obj):
        if obj.video_file:
            return format_html(
                '<video width="320" height="180" controls style="max-width: 100%; height: auto;">'
                '<source src="{}" type="video/mp4">'
                'Ваш браузер не поддерживает данный формат видео.'
                '</video>',
                obj.video_file.url
            )
        return "Видеофайл не загружен"