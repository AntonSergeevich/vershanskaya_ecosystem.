from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.constants import ARCHETYPE_CHOICES

from .storage import protected_storage


class Course(models.Model):
    ACCESS_CHOICES = [
        ('free', 'Бесплатный — «Искатель»'),
        ('paid', 'Платный курс — разовая покупка'),
        ('club', 'Только для членов клуба — «Творец»'),
        ('mage', 'Только личное ведение — «Маг»'),
    ]

    title = models.CharField("Название курса", max_length=255)
    slug = models.SlugField("URL-слаг", unique=True)
    description = models.TextField("Описание")
    cover = models.ImageField("Обложка", upload_to="courses/", blank=True, null=True)
    access_level = models.CharField("Уровень доступа", max_length=10, choices=ACCESS_CHOICES, default='free')
    price = models.DecimalField("Цена (если платный)", max_digits=10, decimal_places=2, default=0.00)
    for_archetype = models.CharField(
        "Рекомендован архетипу", max_length=20, choices=ARCHETYPE_CHOICES, blank=True,
        help_text="Если заполнено, курс поднимается наверх у людей с этим архетипом.")
    order = models.PositiveIntegerField("Порядок", default=100)
    is_published = models.BooleanField("Опубликован", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('lms:course', kwargs={'slug': self.slug})

    # --- Доступ ------------------------------------------------------------

    @property
    def is_free(self):
        return self.access_level == 'free'

    def is_available_for(self, user):
        """Открыт ли курс целиком для этого пользователя.

        Отдельные уроки могут быть открыты как превью даже в закрытом курсе —
        это проверяет Lesson.is_available_for.
        """
        if self.access_level == 'free':
            return True
        if not (user and user.is_authenticated):
            return False
        if user.is_staff:
            return True
        if self.access_level == 'club':
            return user.has_club_access
        if self.access_level == 'mage':
            return user.has_personal_guidance
        if self.access_level == 'paid':
            # Клуб включает в себя все платные курсы — иначе подписка теряет смысл.
            return user.has_club_access or self.accesses.filter(user=user).exists()
        return False

    def locked_reason(self, user):
        """Человеческое объяснение, почему курс закрыт (для страницы курса)."""
        if self.is_available_for(user):
            return ''
        if not (user and user.is_authenticated):
            return 'Войдите, чтобы открыть этот материал.'
        return {
            'club': 'Материал входит в закрытый клуб «Творец».',
            'paid': 'Курс покупается отдельно или входит в подписку клуба.',
            'mage': 'Материал доступен на личном ведении «Маг».',
        }.get(self.access_level, 'Материал закрыт.')

    # --- Прогресс ----------------------------------------------------------

    @property
    def lesson_count(self):
        return self.lessons.count()

    def progress_for(self, user):
        """Процент пройденных уроков — от него зависит «путь героя» в кабинете."""
        total = self.lesson_count
        if not total or not (user and user.is_authenticated):
            return 0
        done = LessonProgress.objects.filter(
            user=user, lesson__course=self, is_completed=True).count()
        return round(done / total * 100)


class Module(models.Model):
    """Раздел внутри курса.

    Не обязателен: короткие курсы живут плоским списком уроков, а длинные
    разбиваются на блоки, чтобы программа не выглядела бесконечной.
    """
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules',
                               verbose_name="Курс")
    title = models.CharField("Название раздела", max_length=255)
    description = models.TextField("Описание", blank=True)
    order = models.PositiveIntegerField("Порядок", default=1)

    class Meta:
        verbose_name = "Раздел курса"
        verbose_name_plural = "Разделы курса"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons', verbose_name="Курс")
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, blank=True, null=True,
                               related_name='lessons', verbose_name="Раздел")
    title = models.CharField("Название урока", max_length=255)
    order = models.PositiveIntegerField("Порядковый номер", default=1)

    video_file = models.FileField(
        "Видеофайл (загрузка на сайт)",
        upload_to="lessons/videos/%Y/%m/",
        storage=protected_storage,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi', 'mkv', 'webm'])],
        help_text="Файл хранится вне публичной папки и отдаётся только тем, у кого есть доступ."
    )
    video_url = models.URLField("Ссылка на видео (альтернатива)", blank=True, null=True,
                                help_text="Используйте, если видео загружено на внешнюю платформу")
    duration_minutes = models.PositiveIntegerField("Длительность, мин", default=0)

    content = models.TextField("Текстовые материалы / Описание", blank=True, null=True)
    is_preview = models.BooleanField("Доступен для предпросмотра", default=False,
                                     help_text="Открыт всем, даже если курс закрытый.")

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.course.title} — {self.order}. {self.title}"

    def get_absolute_url(self):
        return reverse('lms:lesson', kwargs={'slug': self.course.slug, 'pk': self.pk})

    def is_available_for(self, user):
        return self.is_preview or self.course.is_available_for(user)

    @property
    def has_video(self):
        return bool(self.video_file or self.video_url)

    def neighbours(self):
        """Предыдущий и следующий уроки курса — для навигации «дальше»."""
        siblings = list(self.course.lessons.all())
        try:
            index = siblings.index(self)
        except ValueError:
            return None, None
        previous = siblings[index - 1] if index > 0 else None
        following = siblings[index + 1] if index + 1 < len(siblings) else None
        return previous, following


class LessonProgress(models.Model):
    """Отметка о прохождении урока.

    Пишем и незавершённые записи (открыл, но не досмотрел): именно они
    показывают, где человек «залип», и дают повод написать ему первым.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='lesson_progress', verbose_name="Пользователь")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress',
                               verbose_name="Урок")
    is_completed = models.BooleanField("Пройден", default=False)
    started_at = models.DateTimeField("Открыт", auto_now_add=True)
    completed_at = models.DateTimeField("Пройден в", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Прогресс по уроку"
        verbose_name_plural = "Прогресс по урокам"
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'lesson'],
                                    name='lms_unique_progress_per_lesson'),
        ]

    def __str__(self):
        state = "пройден" if self.is_completed else "в процессе"
        return f"{self.user} — {self.lesson.title} ({state})"

    def mark_completed(self):
        """Повторное нажатие не сдвигает дату — первое прохождение важнее."""
        if self.is_completed:
            return self
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
        return self


class CourseAccess(models.Model):
    """Разовая покупка курса вне подписки.

    Подписчикам клуба записи не нужны — им доступ даёт сам факт подписки.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='course_accesses', verbose_name="Пользователь")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='accesses',
                               verbose_name="Курс")
    granted_at = models.DateTimeField("Выдан", auto_now_add=True)
    comment = models.CharField("Основание", max_length=255, blank=True,
                               help_text="Например: «оплата #128» или «подарок».")

    class Meta:
        verbose_name = "Доступ к курсу"
        verbose_name_plural = "Доступы к курсам"
        ordering = ['-granted_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'course'],
                                    name='lms_unique_course_access'),
        ]

    def __str__(self):
        return f"{self.user} → {self.course.title}"
