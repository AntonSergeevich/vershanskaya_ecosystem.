from django.db import models


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
