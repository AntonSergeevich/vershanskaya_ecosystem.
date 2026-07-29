from django.db import models
from django.core.validators import FileExtensionValidator


class Course(models.Model):
    ACCESS_CHOICES = [
        ('free', 'Бесплатный'),
        ('paid', 'Платный курс'),
        ('club', 'Только для членов клуба'),
    ]

    title = models.CharField("Название курса", max_length=255)
    slug = models.SlugField("URL-слаг", unique=True)
    description = models.TextField("Описание")
    cover = models.ImageField("Обложка", upload_to="courses/", blank=True, null=True)
    access_level = models.CharField("Уровень доступа", max_length=10, choices=ACCESS_CHOICES, default='free')
    price = models.DecimalField("Цена (если платный)", max_digits=10, decimal_places=2, default=0.00)
    is_published = models.BooleanField("Опубликован", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

    def __str__(self):
        return self.title


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons', verbose_name="Курс")
    title = models.CharField("Название урока", max_length=255)
    order = models.PositiveIntegerField("Порядковый номер", default=1)

    video_file = models.FileField(
        "Видеофайл (загрузка на сайт)",
        upload_to="lessons/videos/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi', 'mkv', 'webm'])],
        help_text="Загрузите видеофайл в формате MP4, MOV, AVI, MKV или WEBM"
    )
    video_url = models.URLField("Ссылка на видео (альтернатива)", blank=True, null=True,
                                help_text="Используйте, если видео загружено на внешнюю платформу")

    content = models.TextField("Текстовые материалы / Описание", blank=True, null=True)
    is_preview = models.BooleanField("Доступен для предпросмотра", default=False)

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} — {self.order}. {self.title}"