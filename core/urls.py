from django.urls import path
from django.contrib.auth import views as auth_views
from queue_app import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.custom_logout_view, name='logout'),
    path('create-queue/', views.create_queue_view, name='create_queue'),

    # --- Маршруты для панели продавца ---
    # 1. Страница конкретной очереди (QR-код + список клиентов)
    path('queue/<int:pk>/', views.queue_detail, name='queue_detail'),

    # 2. Кнопка "Вызвать следующего"
    path('queue/<int:pk>/call-next/', views.call_next, name='call_next'),

    # 3. Кнопки смены статуса ("Обслужен" / "Не пришел")
    path('queue/<int:pk>/status/<int:item_id>/<str:new_status>/', views.change_status, name='change_status'),

    # 4. Удаление очереди
    path('queue/<int:pk>/delete/', views.delete_queue, name='delete_queue'),
]