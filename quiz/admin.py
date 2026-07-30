from django.contrib import admin

from .models import Answer, Option, Question, Quiz, QuizAttempt


class OptionInline(admin.TabularInline):
    model = Option
    extra = 3
    fields = ('order', 'text', 'archetype', 'weight')


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    fields = ('order', 'text', 'subtitle')
    show_change_link = True


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'question_count', 'attempts_total', 'attempts_completed',
                    'is_published']
    list_filter = ['is_published']
    search_fields = ['title', 'intro']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [QuestionInline]

    @admin.display(description="Вопросов")
    def question_count(self, obj):
        return obj.question_count

    @admin.display(description="Начали")
    def attempts_total(self, obj):
        return obj.attempts.count()

    @admin.display(description="Дошли до результата")
    def attempts_completed(self, obj):
        return obj.attempts.filter(is_completed=True).count()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text', 'quiz', 'order']
    list_filter = ['quiz']
    list_editable = ['order']
    search_fields = ['text']
    inlines = [OptionInline]


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ('question', 'option', 'created_at')
    readonly_fields = ('question', 'option', 'created_at')
    can_delete = False


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'quiz', 'user', 'contact_name', 'contact_phone',
                    'result_archetype', 'progress_percent', 'is_completed', 'created_at']
    list_filter = ['quiz', 'is_completed', 'result_archetype', 'created_at']
    search_fields = ['contact_name', 'contact_phone', 'contact_telegram',
                     'user__username', 'user__email']
    readonly_fields = ['created_at', 'completed_at', 'session_key', 'progress_percent']
    inlines = [AnswerInline]
    ordering = ['-created_at']

    @admin.display(description="Прогресс, %")
    def progress_percent(self, obj):
        return obj.progress_percent
