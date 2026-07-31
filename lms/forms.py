"""Формы студии: Екатерина ведёт курсы отсюда, а не из админки Django.

Админка умеет всё, но выглядит как панель программиста и требует помнить,
что «сохранить и продолжить» — это одна кнопка, а «сохранить» — другая.
Здесь те же поля, но в оформлении сайта и без лишнего.
"""
from django import forms

from .models import Course, Lesson, Module
from .utils import unique_slug


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'description', 'cover', 'access_level', 'price',
                  'for_archetype', 'order', 'is_published']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }
        help_texts = {
            'order': "Чем меньше число, тем выше курс в списке.",
            'is_published': "Снимите галочку, пока курс не готов — его не увидит никто.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].help_text = "Только для платного курса. Иначе оставьте 0."
        self.fields['for_archetype'].required = False

    def save(self, commit=True):
        course = super().save(commit=False)
        # Слаг не спрашиваем: он нужен только адресу и в интерфейсе Екатерины
        # был бы полем «а это ещё зачем?». Считаем из названия.
        if not course.slug or 'title' in self.changed_data:
            course.slug = unique_slug(Course, course.title, exclude_pk=course.pk)
        if commit:
            course.save()
        return course


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ['title', 'description', 'order']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['title', 'module', 'duration_minutes', 'video_file', 'video_url',
                  'content', 'is_preview']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 10}),
        }

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course if course is not None else getattr(self.instance, 'course', None)
        # В списке разделов — только разделы этого курса, иначе урок можно
        # положить в чужой курс и потерять его из виду.
        self.fields['module'].queryset = Module.objects.filter(course=self.course)
        self.fields['module'].empty_label = "Без раздела"
        self.fields['module'].required = False
        self.fields['video_file'].required = False
        self.fields['video_url'].required = False
        self.fields['duration_minutes'].help_text = "Примерно, для строки в программе курса."

    def clean(self):
        data = super().clean()
        # Оба поля разом — частая ошибка: страница урока покажет только файл,
        # и ссылка тихо не сработает.
        if data.get('video_file') and data.get('video_url'):
            self.add_error('video_url',
                           "Оставьте что-то одно: либо загруженный файл, либо ссылку.")
        return data

    def save(self, commit=True):
        lesson = super().save(commit=False)
        if self.course is not None:
            lesson.course = self.course
        if not lesson.pk:
            # Новый урок встаёт в конец программы: угадывать место за автора
            # хуже, чем дать переставить стрелками.
            last = Lesson.objects.filter(course=lesson.course).order_by('-order').first()
            lesson.order = (last.order + 1) if last else 1
        if commit:
            lesson.save()
        return lesson
