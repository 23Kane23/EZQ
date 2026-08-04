import io
import os
import base64
import qrcode
import requests

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Count, Q
from asgiref.sync import async_to_sync

from .forms import CustomRegisterForm
from .models import Queue, QueueItem
from .bot import notify_queue_shift


def send_telegram_message(telegram_id, text):
    """Вспомогательная функция для надежной отправки сообщений в Telegram"""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token or not telegram_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.json().get("ok", False)
    except Exception as e:
        print(f"Ошибка при отправке в Telegram: {e}")
        return False


def register_view(request):
    if request.method == 'POST':
        form = CustomRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = CustomRegisterForm()

    return render(request, 'register.html', {'form': form})


def home_view(request):
    queues = []
    if request.user.is_authenticated:
        queues = Queue.objects.filter(owner=request.user)

    return render(request, 'index.html', {'queues': queues})


def login_view(request):
    return render(request, 'login.html')


def custom_logout_view(request):
    logout(request)
    return redirect('home')


@login_required(login_url='login')
def create_queue_view(request):
    if request.method == "POST":
        queue_name = request.POST.get("queue_name")

        if queue_name:
            queue = Queue.objects.create(
                name=queue_name,
                owner=request.user
            )
            return redirect('queue_detail', pk=queue.pk)

    return render(request, "create_queue.html")


@login_required(login_url='login')
@require_POST
def delete_queue(request, pk):
    """Удаление очереди (доступно только владельцу)"""
    queue = get_object_or_404(Queue, pk=pk, owner=request.user)
    queue.delete()
    return redirect('home')


# ----------------------------------------------------
# Управление очередью (Дашборд продавца)
# ----------------------------------------------------

@login_required(login_url='login')
def queue_detail(request, pk):
    """Просмотр конкретной очереди: QR-код, текущий вызванный, список людей и статистика по датам"""
    queue = get_object_or_404(Queue, pk=pk, owner=request.user)

    # 1. Генерация Ссылки и QR-кода
    bot_username = "QueueQueue_bot"  # Укажите username вашего бота без @
    bot_link = f"https://t.me/{bot_username}?start={queue.slug}"

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(bot_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    # 2. Получение списков клиентов
    current_called = queue.items.filter(status='called').first()
    waiting_items = queue.items.filter(status='waiting').order_by('position')
    completed_items = queue.items.filter(status__in=['served', 'cancelled']).order_by('-updated_at')[:10]

    # 3. Агрегация статистики по дням
    daily_stats = (
        queue.items.values('created_at__date')
        .annotate(
            total=Count('id'),
            served=Count('id', filter=Q(status='served')),
            cancelled=Count('id', filter=Q(status='cancelled')),
            waiting=Count('id', filter=Q(status='waiting')),
        )
        .order_by('-created_at__date')
    )

    context = {
        'queue': queue,
        'bot_link': bot_link,
        'qr_code': qr_code_base64,
        'current_called': current_called,
        'waiting_items': waiting_items,
        'completed_items': completed_items,
        'daily_stats': daily_stats,
    }
    return render(request, 'queue_detail.html', context)


@login_required(login_url='login')
@require_POST
def call_next(request, pk):
    """Кнопка 'Вызвать следующего'"""
    queue = get_object_or_404(Queue, pk=pk, owner=request.user)

    # Берём первого человека из очереди
    next_item = queue.items.filter(status='waiting').order_by('position').first()

    if next_item:
        next_item.status = 'called'
        next_item.save()

        # Берём название заведения из имени аккаунта при регистрации
        business_name = queue.owner.first_name or queue.owner.get_full_name() or queue.owner.username

        # В сообщении подставляем название заведения и конкретное окно/кассу
        text = f"🔔 **Ваша очередь подошла!**\n\nПожалуйста, подойдите к **{queue.name}** в **{business_name}**."
        success = send_telegram_message(next_item.user.telegram_id, text)

        if not success:
            messages.warning(request, f"Клиент №{next_item.position} вызван, но сообщение в Telegram не ушло.")
        else:
            messages.success(request, f"Вызван клиент №{next_item.position} ({next_item.user.first_name})")
    else:
        messages.info(request, "В очереди никого нет.")

    return redirect('queue_detail', pk=pk)


@login_required(login_url='login')
@require_POST
def change_status(request, pk, item_id, new_status):
    """Кнопки 'Обслужен' или 'Не пришел'"""
    queue = get_object_or_404(Queue, pk=pk, owner=request.user)
    item = get_object_or_404(QueueItem, id=item_id, queue=queue)

    if new_status in ['served', 'cancelled']:
        item.status = new_status
        item.save()

        # Если обслужен — отправляем благодарность с названием заведения
        if new_status == 'served':
            business_name = queue.owner.first_name or queue.owner.get_full_name() or queue.owner.username
            text = f"🙏 **Спасибо, что посетили нас!**\n\nБудем рады видеть вас снова в **{business_name}**."
            send_telegram_message(item.user.telegram_id, text)

        # Сдвигаем очередь и уведомляем остальных людей
        try:
            async_to_sync(notify_queue_shift)(queue.id)
        except Exception as e:
            print(f"Ошибка при сдвиге очереди: {e}")

    return redirect('queue_detail', pk=pk)