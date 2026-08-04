import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# ----------------------------------------------------
# 1. Инициализация окружения Django
# ----------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

# ----------------------------------------------------
# 2. Импорты aiogram и моделей
# ----------------------------------------------------
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from django.db.models import Max

from queue_app.models import Queue, TelegramUser, QueueItem

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)


# ----------------------------------------------------
# Уведомления о сдвиге очереди
# ----------------------------------------------------
async def notify_queue_shift(queue_id: int):
    @sync_to_async
    def get_waiting_users():
        return list(
            QueueItem.objects.filter(queue_id=queue_id, status='waiting')
            .select_related('user')
            .order_by('position')
        )

    waiting_items = await get_waiting_users()

    for idx, item in enumerate(waiting_items):
        people_ahead = idx
        telegram_id = item.user.telegram_id

        try:
            if people_ahead == 0:
                # Измененный текст: информируем, что человек первый в очереди, но ждет именно кнопки продавца
                text = (
                    f"⏳ **Очередь продвинулась!**\n\n"
                    f" Вы следующий! Ожидайте, скоро вас вызовут к стойке."
                )
            else:
                text = (
                    f"📊 **Очередь продвинулась!**\n\n"
                    f"Перед вами осталось человек: **{people_ahead}**"
                )
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение {telegram_id}: {e}")


# ----------------------------------------------------
# 1. Мгновенная регистрация по QR (/start <slug>)
# ----------------------------------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Посетитель"
    slug = command.args

    if not slug:
        await message.answer("👋 Чтобы встать в очередь, отсканируйте QR-код заведения.")
        return

    @sync_to_async
    def register_and_enqueue():
        # Ищем активную очередь
        try:
            queue = Queue.objects.get(slug=slug, is_active=True)
        except Queue.DoesNotExist:
            return None, None, False, 0

        # Создаем или обновляем пользователя Telegram
        user, _ = TelegramUser.objects.get_or_create(
            telegram_id=user_id,
            defaults={'username': username, 'first_name': first_name}
        )
        if user.first_name != first_name or user.username != username:
            user.first_name = first_name
            user.username = username
            user.save()

        # Проверяем, не стоит ли уже человек в очереди
        existing_item = QueueItem.objects.filter(queue=queue, user=user, status='waiting').first()
        if existing_item:
            people_ahead = QueueItem.objects.filter(
                queue=queue, status='waiting', position__lt=existing_item.position
            ).count()
            return queue, existing_item, False, people_ahead

        # Вычисляем номер очереди
        last_item = QueueItem.objects.filter(queue=queue).aggregate(Max('position'))['position__max'] or 0
        next_position = last_item + 1

        # Создаем талон в очереди
        new_item = QueueItem.objects.create(
            queue=queue,
            user=user,
            position=next_position,
            status='waiting'
        )

        people_ahead = QueueItem.objects.filter(
            queue=queue, status='waiting', position__lt=next_position
        ).count()

        return queue, new_item, True, people_ahead

    queue, item, created, people_ahead = await register_and_enqueue()

    if not queue:
        await message.answer("❌ Заведение не найдено или очередь временно не активна.")
        return

    ahead_text = f"Перед вами людей: **{people_ahead}**" if people_ahead > 0 else "Вы первый в очереди!"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Покинуть очередь", callback_data=f"cancel_{item.id}")]
    ])

    if not created:
        await message.answer(
            f"⚠️ **Вы уже находитесь в очереди!**\n\n"
            f"📍 Заведение: **{queue.name}**\n"
            f"🎫 Ваш номер: **№{item.position}**\n"
            f"👥 {ahead_text}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # Ответ при новом получении номерка
    await message.answer(
        f"✅ **Вы успешно записаны!**\n\n"
        f"📍 Заведение: **{queue.name}**\n"
        f"🎫 Ваш номер: **№{item.position}**\n"
        f"👥 {ahead_text}\n\n"
        f"🔔 Мы будем уведомлять вас о каждом сдвиге очереди!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


# ----------------------------------------------------
# 2. Отмена записи по кнопке
# ----------------------------------------------------
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_queue_handler(callback: types.CallbackQuery):
    item_id = int(callback.data.split("_")[1])

    @sync_to_async
    def cancel_ticket():
        try:
            item = QueueItem.objects.get(id=item_id, user__telegram_id=callback.from_user.id)
            if item.status == 'waiting':
                item.status = 'cancelled'
                item.save()
                return item.queue_id
        except QueueItem.DoesNotExist:
            return None
        return None

    queue_id = await cancel_ticket()

    if queue_id:
        await callback.message.edit_text("❌ Вы отменили свою запись и вышли из очереди.")
        await notify_queue_shift(queue_id)
    else:
        await callback.answer("Запись не найдена или уже завершена.", show_alert=True)


# ----------------------------------------------------
# Точка входа
# ----------------------------------------------------
async def main():
    print("🚀 Бот запущен (мгновенный режим)!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())