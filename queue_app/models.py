import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


class Queue(models.Model):
    """Модель самой очереди (создается владельцем бизнеса через сайт)"""
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='queues',
        verbose_name="Владелец (Компания)"
    )
    name = models.CharField(max_length=255, verbose_name="Название очереди")
    slug = models.SlugField(
        unique=True, 
        blank=True, 
        help_text="Уникальный код для QR (например, my-cafe-1)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активна ли очередь")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Очередь"
        verbose_name_plural = "Очереди"

    def save(self, *args, **kwargs):
        # Автоматическая генерация уникального slug при сохранении
        if not self.slug:
            base_slug = slugify(self.name)

            # Если slugify вернул пустую строку (например, при кириллице без транслитератора)
            if not base_slug:
                base_slug = "queue"

            slug = base_slug
            # Проверяем уникальность и при необходимости добавляем короткий UUID
            while Queue.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        company_name = self.owner.last_name or self.owner.username
        return f"{self.name} ({company_name})"


class TelegramUser(models.Model):
    """Посетители, которые сканируют QR-код и встают в очередь"""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=150, blank=True, null=True, verbose_name="Username")
    first_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Имя")

    class Meta:
        verbose_name = "Пользователь Telegram"
        verbose_name_plural = "Пользователи Telegram"

    def __str__(self):
        return f"{self.first_name or 'Пользователь'} (@{self.username or self.telegram_id})"


class QueueItem(models.Model):
    """Записи людей в конкретной очереди"""
    STATUS_CHOICES = [
        ('waiting', 'Ожидает'),
        ('called', 'Вызван'),
        ('served', 'Обслужен'),
        ('cancelled', 'Отменил/Не пришел'),
    ]

    queue = models.ForeignKey(
        Queue,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Очередь"
    )
    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name='queue_entries',
        verbose_name="Посетитель"
    )
    position = models.PositiveIntegerField(verbose_name="Номер в очереди")
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='waiting', 
        verbose_name="Статус"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        ordering = ['position']
        verbose_name = "Запись в очереди"
        verbose_name_plural = "Записи в очереди"

    def __str__(self):
        return f"№{self.position} - {self.user} ({self.get_status_display()})"