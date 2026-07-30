from django.db import models


class SiteProfile(models.Model):
    """Лицо и голос сайта: портрет, приветствие, короткий рассказ о себе.

    Живёт в базе, а не в шаблоне: сменить фотографию или переписать первый
    экран — задача Екатерины, а не повод выкатывать релиз.

    Запись всегда одна: `SiteProfile.load()` возвращает её и создаёт при
    первом обращении, поэтому шаблонам не нужно ничего проверять.
    """
    name = models.CharField("Имя на сайте", max_length=120,
                            default="Екатерина Вершанская")
    role = models.CharField("Кто вы", max_length=160, blank=True,
                            default="Психолог, работаю с архетипами")

    headline = models.CharField(
        "Заголовок первого экрана", max_length=200,
        default="Понять, кто вы, и перестать жить чужую жизнь",
        help_text="Слова в *звёздочках* будут выделены курсивом и цветом.")
    lead = models.TextField(
        "Текст под заголовком",
        default="Начнём не с советов, а с вопроса о вас. Семь вопросов — и станет "
                "видно, какой архетип ведёт вас сейчас, где вы теряете силы "
                "и с чего начинать.")

    portrait = models.ImageField("Портрет", upload_to="profile/", blank=True, null=True,
                                 help_text="Вертикальное фото. Лучше всего 4:5, лицо ближе к верху.")
    portrait_note = models.CharField(
        "Подпись у портрета", max_length=120, blank=True,
        default="Веду разборы с 2019 года",
        help_text="Маленькая карточка поверх фотографии. Оставьте пустой, чтобы убрать.")

    about_title = models.CharField("Заголовок блока «о себе»", max_length=200, blank=True,
                                   default="Коротко о себе")
    about_text = models.TextField(
        "Текст блока «о себе»", blank=True,
        default="Я не даю универсальных советов и не обещаю, что всё наладится за "
                "неделю. Моя работа — помочь увидеть, по какому сценарию вы живёте "
                "сейчас и какой шаг в нём действительно ваш.")
    about_photo = models.ImageField("Второе фото", upload_to="profile/", blank=True, null=True,
                                    help_text="Необязательно. Показывается в блоке «о себе».")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Профиль сайта"
        verbose_name_plural = "Профиль сайта"

    def __str__(self):
        return self.name

    @classmethod
    def load(cls):
        """Единственная запись профиля. Создаётся сама при первом обращении."""
        profile, _ = cls.objects.get_or_create(pk=1)
        return profile

    def save(self, *args, **kwargs):
        # Жёстко держим один экземпляр: вторая запись означала бы, что часть
        # страниц показывает старое фото.
        self.pk = 1
        super().save(*args, **kwargs)


class Testimonial(models.Model):
    """Отзыв участницы клуба — социальное доказательство на лендинге."""
    author = models.CharField("Имя автора", max_length=120)
    role = models.CharField("Кто это", max_length=160, blank=True,
                            help_text="Например: «участница клуба, 8 месяцев»")
    text = models.TextField("Текст отзыва")
    photo = models.ImageField("Фото", upload_to="testimonials/", blank=True, null=True)
    order = models.PositiveIntegerField("Порядок", default=100)
    is_published = models.BooleanField("Опубликован", default=True)

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.author} — {self.text[:40]}"


class FAQItem(models.Model):
    """Блок «частые вопросы» — снимает возражения перед оплатой."""
    question = models.CharField("Вопрос", max_length=255)
    answer = models.TextField("Ответ")
    order = models.PositiveIntegerField("Порядок", default=100)
    is_published = models.BooleanField("Опубликован", default=True)

    class Meta:
        verbose_name = "Вопрос-ответ"
        verbose_name_plural = "Частые вопросы"
        ordering = ['order', 'id']

    def __str__(self):
        return self.question
