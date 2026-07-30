from django.db import models
from django.urls import reverse


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


class LegalInfo(models.Model):
    """Реквизиты продавца.

    Нужны в трёх местах сразу: в подвале, на странице реквизитов и внутри
    текстов оферты с политикой. Хранение в одном месте избавляет от ситуации,
    когда ИНН на странице один, а в оферте — старый.

    Запись всегда одна, как и у SiteProfile.
    """
    ENTITY_CHOICES = [
        ('self_employed', 'Самозанятый (НПД)'),
        ('ip', 'Индивидуальный предприниматель'),
        ('ooo', 'ООО'),
    ]

    entity_type = models.CharField("Форма", max_length=20, choices=ENTITY_CHOICES,
                                   default='self_employed')
    legal_name = models.CharField("Полное наименование", max_length=255, blank=True,
                                  help_text="Например: ИП Вершанская Екатерина Сергеевна")
    inn = models.CharField("ИНН", max_length=12, blank=True)
    ogrn = models.CharField("ОГРН / ОГРНИП", max_length=15, blank=True)
    address = models.CharField("Адрес", max_length=255, blank=True)
    email = models.EmailField("Email для обращений", blank=True)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    site_url = models.URLField("Адрес сайта", blank=True,
                               help_text="Подставляется в тексты документов.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Реквизиты"
        verbose_name_plural = "Реквизиты"

    def __str__(self):
        return self.legal_name or "Реквизиты не заполнены"

    @classmethod
    def load(cls):
        info, _ = cls.objects.get_or_create(pk=1)
        return info

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def is_filled(self):
        """Без ИНН и наименования документы публиковать нельзя."""
        return bool(self.legal_name and self.inn)

    def tokens(self):
        """Подстановки для текстов документов."""
        return {
            '{НАИМЕНОВАНИЕ}': self.legal_name or '—',
            '{ИНН}': self.inn or '—',
            '{ОГРН}': self.ogrn or '—',
            '{АДРЕС}': self.address or '—',
            '{EMAIL}': self.email or '—',
            '{ТЕЛЕФОН}': self.phone or '—',
            '{САЙТ}': self.site_url or '—',
        }


class LegalPage(models.Model):
    """Оферта, политика и прочие документы.

    Текст правится в админке: юрист присылает формулировки, Екатерина
    вставляет — без участия разработчика и без выкатки.
    """
    slug = models.SlugField("Адрес", unique=True,
                            help_text="Например: oferta — страница будет /dokumenty/oferta/")
    title = models.CharField("Заголовок", max_length=200)
    summary = models.CharField("Короткое пояснение", max_length=300, blank=True,
                               help_text="Одна строка под заголовком, человеческим языком.")
    body = models.TextField(
        "Текст документа",
        help_text="Можно использовать подстановки: {НАИМЕНОВАНИЕ}, {ИНН}, {ОГРН}, "
                  "{АДРЕС}, {EMAIL}, {ТЕЛЕФОН}, {САЙТ} — они заменятся на реквизиты.")
    is_published = models.BooleanField("Опубликован", default=False,
                                       help_text="Черновик виден только сотрудникам.")
    show_in_footer = models.BooleanField("Ссылка в подвале", default=True)
    order = models.PositiveIntegerField("Порядок", default=100)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Правовой документ"
        verbose_name_plural = "Правовые документы"
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('core:legal', kwargs={'slug': self.slug})

    def rendered_body(self):
        """Текст с подставленными реквизитами."""
        text = self.body
        for token, value in LegalInfo.load().tokens().items():
            text = text.replace(token, value)
        return text


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
