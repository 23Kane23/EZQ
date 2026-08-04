# queue_app/services.py
import requests
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")


def send_telegram_message(telegram_id: int, text: str):
    """Отправка сообщения через Telegram Bot API без использования aiogram в admin.py"""
    if not BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки сообщения Telegram: {e}")


def notify_queue_shift_sync(business_id: int):
    """Снхронная функция пересчета и отправки обновлений всем участникам"""
    from .models import QueueItem

    waiting_items = list(
        QueueItem.objects.filter(business_id=business_id, status='waiting')
        .select_related('user')
        .order_by('position')
    )

    for idx, item in enumerate(waiting_items):
        people_ahead = idx
        telegram_id = item.user.telegram_id

        if people_ahead == 0:
            text = (
                "⚡ **Очередь продвинулась!**\n\n"
                "🎉 **Вы следующий!** Пожалуйста, будьте готовы."
            )
        else:
            text = (
                f"📊 **Очередь продвинулась!**\n\n"
                f"Перед вами осталось человек: **{people_ahead}**"
            )
        send_telegram_message(telegram_id, text)
