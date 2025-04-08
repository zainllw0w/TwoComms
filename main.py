import asyncio
from app.keep_alive import keep_alive
import aiohttp
import json
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ContentType,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv

from app import buttons as kb
from app import database as db
import asyncio
import logging
from aiogram import Bot
from app.database import get_orders_not_delivered, update_order_status
from app.database import get_order_by_id


# Загрузка переменных окружения
load_dotenv()
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
PRODUCTS_JSON_PATH = 'app/products.json'

# Определение состояний FSM
class AdminTtnFlow(StatesGroup):
    waiting_for_city = State()         # Ждём, выберут город отправки (Киев/Харьков)
    waiting_for_payer = State()        # Ждём, кто платит (наложка или отправитель)
    waiting_for_sender_branch = State() # Ждём ввод номера отделения, откуда отправляем
    waiting_for_confirm = State()       # Показываем сводку, ждём подтверждения или «ввести заново»
    waiting_for_manual_data = State()   # (опционально) если при создании ТТН возникла ошибка, просим ввести вручную

class OrderStates(StatesGroup):
    waiting_for_size = State()
    waiting_for_options = State()
    waiting_for_payment_method = State()
    waiting_for_city = State()
    waiting_for_branch = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_payment_confirmation = State()
    waiting_for_payment_screenshot = State()
    waiting_for_paid_confirmation = State()

class DiscountStates(StatesGroup):
    waiting_for_ubd_photo = State()
    waiting_for_repost_screenshot = State()

class SupportStates(StatesGroup):
    waiting_for_issue_description = State()
    waiting_for_user_response = State()

class AdminInputStates(StatesGroup):
    admin_support_reply = State()
    order_rejection_reason = State()
    payment_rejection_reason = State()
    waiting_for_ttn = State()
    waiting_for_receipt = State()
    waiting_for_print_description = State()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Команда /start
@dp.message(Command('start'))
async def cmd_start(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer('👋 Вітаємо, Адміністратор!', reply_markup=kb.admin_main_menu())
    else:
        await message.answer('👋 Вітаємо в нашому магазині! Оберіть опцію:', reply_markup=kb.main_menu())

# Обработка кнопки "🔙 На головну"
@dp.message(F.text == '🔙 На головну')
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer('🔙 Повертаємось до головного меню.', reply_markup=kb.admin_main_menu())
    else:
        await message.answer('🔙 Повертаємось до головного меню.', reply_markup=kb.main_menu())

# Обработка раздела "Мої замовлення"
@dp.message(F.text == '📦 Мої замовлення')
async def my_orders(message: Message):
    orders = await db.get_orders_by_user(message.from_user.id)
    if not orders:
        await message.answer(
            "🛒 У вас немає замовлень.",
            reply_markup=kb.no_orders_menu()
        )
        return

    for order in orders:
        order_text = await format_order_text(order, order['id'], message.from_user.username, message.from_user.id)
        status = order.get('status', '❓ Невідомий')
        await message.answer(
            f"{order_text}\n\n🟢 Статус: {status}",
            reply_markup=kb.order_details_button(order['id'])
        )


# Обработка кнопки "🛠️ Оформити замовлення в конструкторі"
@dp.message(F.text == '🛠️ Оформити замовлення в конструкторі')
async def go_to_constructor(message: Message):
    await message.answer(
        '🛠️ Оберіть категорію:',
        reply_markup=kb.category_selection_menu()
    )


# Обработка раздела "Конструктор замовлення"
@dp.message(F.text == '⚙️ Конструктор замовлення ⚙️')
async def constructor_order(message: Message):
    await message.answer(
        '🛠️ Оберіть категорію:',
        reply_markup=kb.category_selection_menu()
    )


# Обработка выбора категории (Футболки или Худі)
@dp.message(F.text.in_(['👕 Футболки', '🥷🏼 Худі']))
async def select_category(message: Message, state: FSMContext):
    category = 't_shirts' if message.text == '👕 Футболки' else 'hoodies'

    # Устанавливаем изначально включённые опции
    if category == 't_shirts':
        default_options = {
            'made_in_ukraine': True,
            'back_text': True,
            'back_print': True
        }
    else:  # hoodies
        default_options = {
            'sleeve_text': True,
        }

    # Сохраняем в state
    await state.update_data(category=category, options=default_options)

    await message.answer(
        '📏 Оберіть розмір:',
        reply_markup=kb.size_selection_menu()
    )
    await state.set_state(OrderStates.waiting_for_size)


# Обработка нажатия на кнопку "📏 Розмірна сітка"
@dp.callback_query(OrderStates.waiting_for_size, F.data == 'size_chart')
async def size_chart(callback: CallbackQuery):
    await callback.message.answer("📏 Розмірна сітка скоро буде доступна.")
    await callback.answer()


# Обработка выбора размера (инлайн-кнопки)
@dp.callback_query(OrderStates.waiting_for_size, F.data.startswith('size_'))
async def select_size(callback: CallbackQuery, state: FSMContext):
    valid_sizes = ['S', 'M', 'L', 'XL', 'XXL']
    size = callback.data.split('_')[1]
    if size not in valid_sizes:
        return
    # Сохраняем выбранный размер
    await state.update_data(size=size)
    # Сразу показываем дисплей продукта
    await display_product(callback.from_user.id, state)
    # Можно очистить состояние или оставить
    # await state.clear()   # если нужно
    await callback.answer()


# Обработка кнопки "🔙 На головну" в состоянии выбора размера
@dp.message(OrderStates.waiting_for_size, F.text == '🔙 На головну')
async def back_to_main_from_size(message: Message, state: FSMContext):
    await back_to_main(message, state)


# Обработка нажатий на опции
@dp.callback_query(F.data.startswith('option_'))
async def toggle_option(callback: CallbackQuery, state: FSMContext):
    # Получаем ключ опции, например "made_in_ukraine"
    option_key = callback.data.split('_', maxsplit=1)[1]
    # Забираем текущие данные из FSM
    data = await state.get_data()
    # Словарь с выбранными опциями
    selected_options = data.get('options', {})
    # Переключаем значение (True -> False / False -> True)
    current_value = selected_options.get(option_key, False)
    selected_options[option_key] = not current_value
    # Сохраняем обратно в FSM
    await state.update_data(options=selected_options)
    # Вызываем display_product, чтобы обновить сообщение (с новыми галочками, ценой и т.п.)
    await display_product(callback.from_user.id, state)
    # Закрываем «круг» коллбэка
    await callback.answer()


# Обработка кнопки "➡️ Далі"
@dp.callback_query(OrderStates.waiting_for_options, F.data == 'options_next')
async def proceed_to_product(callback: CallbackQuery, state: FSMContext):
    await display_product(callback.from_user.id, state)
    await state.set_state(None)
    await callback.answer()


# Функция для отображения продукта
from aiogram.types import InputMediaPhoto


async def display_product(user_id, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')
    current_index = data.get('current_index', 0)
    current_color_index = data.get('current_color_index', 0)

    if not os.path.exists(PRODUCTS_JSON_PATH):
        await bot.send_message(user_id, "❌ Файла з товарами не знайдено.")
        return

    with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
        products = json.load(f)

    category_products = products.get(category, [])
    total_products = len(category_products)

    if current_index < 0 or current_index >= total_products:
        current_index = 0
        await state.update_data(current_index=current_index)

    product = category_products[current_index]
    model_name = product.get('model_name')
    colors = product.get('colors', [])
    total_colors = len(colors)

    if current_color_index < 0 or current_color_index >= total_colors:
        current_color_index = 0
        await state.update_data(current_color_index=current_color_index)

    selected_color_url = colors[current_color_index]
    # Для футболок добавляем cache buster
    image_url = selected_color_url


    await state.update_data(selected_product=product, selected_color_index=current_color_index)

    price, discount_text = await calculate_price(product, user_id)
    await state.update_data(price=price)

    selected_options = data.get('options', {})

    # Формируем описание выбранных опций
    options_text = ""
    if category == 't_shirts':
        if selected_options.get('made_in_ukraine'):
            options_text += "✅ Принт біля шиї\n"
        else:
            options_text += "❌ Принт біля шиї\n"
        if selected_options.get('back_text'):
            options_text += "✅ Задній підпис\n"
        else:
            options_text += "❌ Задній підпис\n"
        if selected_options.get('back_print'):
            options_text += "✅ Великий принт на спину\n"
        else:
            options_text += "❌ Великий принт на спину\n"
    elif category == 'hoodies':
        # Добавьте опции для худі, если нужно
        pass

    options_text = "\n**Вибрані опції:**\n" + options_text

    order_summary = (
        f"📝 **Ваше замовлення:**\n"
        f"🔹 **Товар:** {model_name}\n"
        f"📏 **Розмір:** {data.get('size')}\n"
        f"🎨 **Колір:** {current_color_index + 1} з {total_colors}\n"
        f"💸 **Сума до оплати:** {price} грн\n"
        f"{discount_text}"
        f"{options_text}"
    )

    # Генерируем клавиатуру, передавая выбранные опции
    keyboard = kb.product_display_keyboard(current_index, total_products, current_color_index, total_colors, category,
                                           selected_options)

    product_message_id = data.get('product_message_id')
    if product_message_id:
        try:
            await bot.edit_message_media(
                chat_id=user_id,
                message_id=product_message_id,
                media=InputMediaPhoto(media=image_url, caption=order_summary, parse_mode='Markdown'),
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error editing product photo: {e}")
    else:
        try:
            msg = await bot.send_photo(
                user_id,
                photo=image_url,
                caption=order_summary,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            await state.update_data(product_message_id=msg.message_id)
            logger.info(f"Displayed product to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending product photo: {e}")


# Обработка кнопок пагинации по моделям
@dp.callback_query(F.data.in_(['next_product', 'prev_product']))
async def paginate_products(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')
    current_index = data.get('current_index', 0)
    current_color_index = 0

    if not os.path.exists(PRODUCTS_JSON_PATH):
        await bot.send_message(callback.from_user.id, "❌ Файла з товарами не знайдено.")
        await callback.answer()
        return

    with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
        products = json.load(f)

    category_products = products.get(category, [])
    total_products = len(category_products)

    if callback.data == 'next_product':
        current_index += 1
        if current_index >= total_products:
            current_index = 0
    elif callback.data == 'prev_product':
        current_index -= 1
        if current_index < 0:
            current_index = total_products - 1

    await state.update_data(current_index=current_index, current_color_index=current_color_index)

    await display_product(callback.from_user.id, state)
    await callback.answer()


# Обработка кнопок переключения цветов
@dp.callback_query(F.data.in_(['next_color', 'prev_color']))
async def paginate_colors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')
    current_index = data.get('current_index', 0)
    current_color_index = data.get('current_color_index', 0)

    if not os.path.exists(PRODUCTS_JSON_PATH):
        await bot.send_message(callback.from_user.id, "❌ Файла з товарами не знайдено.")
        await callback.answer()
        return

    with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
        products = json.load(f)

    category_products = products.get(category, [])
    total_products = len(category_products)

    product = category_products[current_index]
    colors = product.get('colors', [])
    total_colors = len(colors)

    if callback.data == 'next_color':
        current_color_index += 1
        if current_color_index >= total_colors:
            current_color_index = 0
    elif callback.data == 'prev_color':
        current_color_index -= 1
        if current_color_index < 0:
            current_color_index = total_colors - 1

    await state.update_data(current_color_index=current_color_index)

    await display_product(callback.from_user.id, state)
    await callback.answer()


# Обработка кнопки "✅ Вибрати"
@dp.callback_query(F.data == 'select_product')
async def select_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('category')
    size = data.get('size')
    current_index = data.get('current_index', 0)
    current_color_index = data.get('current_color_index', 0)
    selected_options = data.get('options', {})

    if not os.path.exists(PRODUCTS_JSON_PATH):
        await bot.send_message(callback.from_user.id, "❌ Файла з товарами не знайдено.")
        await callback.answer()
        return

    with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
        products = json.load(f)

    category_products = products.get(category, [])
    total_products = len(category_products)

    if current_index < 0 or current_index >= total_products:
        await state.update_data(current_index=0)
        current_index = 0

    product = category_products[current_index]
    model_name = product.get('model_name')
    colors = product.get('colors', [])
    total_colors = len(colors)

    if current_color_index < 0 or current_color_index >= total_colors:
        current_color_index = 0
        await state.update_data(current_color_index=current_color_index)

    selected_color_url = colors[current_color_index]

    await state.update_data(selected_product=product, selected_color_index=current_color_index)
    await state.update_data(product_message_id=None)

    price, discount_text = await calculate_price(product, callback.from_user.id)
    await state.update_data(price=price)

    options_text = ""
    if category == 't_shirts':
        if selected_options.get('made_in_ukraine'):
            options_text += "✅ Made in Ukraine принт\n"
        if selected_options.get('back_text'):
            options_text += "✅ Задній підпис\n"
        if selected_options.get('back_print'):
            options_text += "✅ Задній принт\n"
    elif category == 'hoodies':
        if selected_options.get('collar'):
            options_text += "✅ Горловина\n"
        if selected_options.get('sleeve_text'):
            options_text += "✅ Надписи на рукавах\n"
        if selected_options.get('back_print'):
            options_text += "✅ Задній принт\n"

    if options_text:
        options_text = "\n**Вибрані опції:**\n" + options_text
    else:
        options_text = "\n**Вибрані опції:**\n❌ Немає"

    order_summary = (
        f"📝 **Ваше замовлення:**\n"
        f"🔹 **Товар:** {model_name}\n"
        f"📏 **Розмір:** {size}\n"
        f"🎨 **Колір:** {current_color_index + 1} з {total_colors}\n"
        f"💸 **Сума до оплати:** {price} грн\n"
        f"{discount_text}"
        f"{options_text}"
    )

    await callback.message.answer(
        order_summary,
        reply_markup=kb.payment_options(),
        parse_mode='Markdown'
    )
    await state.set_state(OrderStates.waiting_for_payment_method)
    await callback.answer()


# Обработка выбора способа оплаты
@dp.callback_query(OrderStates.waiting_for_payment_method, F.data.in_(['payment_card', 'payment_post']))
async def payment_method_selected(callback: CallbackQuery, state: FSMContext):
    payment_method = 'card' if callback.data == 'payment_card' else 'cash'
    await state.update_data(payment_method=payment_method)

    await callback.message.answer("🏙️ Введіть ваше місто:")
    await state.set_state(OrderStates.waiting_for_city)
    await callback.answer()


# Обработка ввода города
@dp.message(OrderStates.waiting_for_city)
async def order_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("🏢 Введіть номер відділення Нової Пошти:")
    await state.set_state(OrderStates.waiting_for_branch)


# Обработка ввода отделения
@dp.message(OrderStates.waiting_for_branch)
async def order_branch(message: Message, state: FSMContext):
    await state.update_data(branch=message.text)
    await message.answer("🧑 Введіть ваше ПІБ:")
    await state.set_state(OrderStates.waiting_for_name)


# Обработка ввода имени
@dp.message(OrderStates.waiting_for_name)
async def order_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📞 Введіть ваш номер телефону:")
    await state.set_state(OrderStates.waiting_for_phone)


# Обработка ввода телефона с валидацией
@dp.message(OrderStates.waiting_for_phone)
async def order_phone(message: Message, state: FSMContext):
    phone_number = message.text.strip()
    if not phone_number:
        await message.answer("❌ Будь ласка, введіть коректний номер телефону.")
        return

    await state.update_data(phone=phone_number)
    data = await state.get_data()
    payment_method = data.get('payment_method')

    if payment_method == 'cash':
        order_data = {
            'product': data.get('selected_product')['model_id'],
            'size': data.get('size'),
            'city': data.get('city'),
            'branch': data.get('branch'),
            'name': data.get('name'),
            'phone': data.get('phone'),
            'payment_method': payment_method,
            'status': 'Нове',
            'user_id': message.from_user.id,
            'back_print': data.get('options', {}).get('back_print', False),
            'back_text': data.get('options', {}).get('back_text', False),
            'made_in_ukraine': data.get('options', {}).get('made_in_ukraine', False),
            'collar': data.get('options', {}).get('collar', False),
            'sleeve_text': data.get('options', {}).get('sleeve_text', False),
            'price': data.get('price'),
            'selected_color_index': data.get('selected_color_index', 0)
        }

        order_id = await db.save_order(message.from_user.id, order_data)

        await message.answer("✅ Ваше замовлення прийнято та буде оброблено найближчим часом. Дякуємо!")
        await state.clear()

        order = await db.get_order_by_id(order_id)
        order_text = await format_order_text(order, order_id, message.from_user.username, message.from_user.id)
        image_url = await get_order_image_url(order)
        statuses = get_statuses_from_order_status(order['status'])
        admin_message = await bot.send_photo(
            ADMIN_ID,
            photo=image_url,
            caption=f"📦 **Нове замовлення #{order_id}** від @{message.from_user.username}:\n{order_text}",
            reply_markup=kb.admin_order_actions(order_id, statuses=statuses)
        )
        await db.save_order_admin_message_id(order_id, admin_message.message_id)
    else:
        selected_product = data.get('selected_product')
        price = data.get('price')
        discount_text = ''

        await message.answer(
            f"💳 **Оплата на карту**\n\n"
            f"💰 **Сума до оплати:** {price} грн\n"
            f"💳 **Реквізити для оплати:**\n"
            "```\n4441111140615463\n```"
            f"{discount_text}\n\n"
            f"Після оплати натисніть кнопку 'Оплачено' і надішліть скріншот квитанції.",
            parse_mode='Markdown',
            reply_markup=kb.paid_button()
        )
        await state.set_state(OrderStates.waiting_for_paid_confirmation)


# Обработка нажатия на кнопку "Оплачено"
@dp.callback_query(OrderStates.waiting_for_paid_confirmation, F.data == 'paid_confirmed')
async def paid_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📸 Будь ласка, надішліть скріншот квитанції про оплату.")
    await state.set_state(OrderStates.waiting_for_payment_screenshot)
    await callback.answer()


# Обработка получения скриншота оплаты
@dp.message(OrderStates.waiting_for_payment_screenshot, F.content_type == ContentType.PHOTO)
async def receive_payment_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()

    order_data = {
        'product': data.get('selected_product')['model_id'],
        'size': data.get('size'),
        'city': data.get('city'),
        'branch': data.get('branch'),
        'name': data.get('name'),
        'phone': data.get('phone'),
        'payment_method': 'card',
        'status': 'Очікується підтвердження оплати',
        'user_id': message.from_user.id,
        'back_print': data.get('options', {}).get('back_print', False),
        'back_text': data.get('options', {}).get('back_text', False),
        'made_in_ukraine': data.get('options', {}).get('made_in_ukraine', False),
        'collar': data.get('options', {}).get('collar', False),
        'sleeve_text': data.get('options', {}).get('sleeve_text', False),
        'price': data.get('price'),
        'selected_color_index': data.get('selected_color_index', 0)
    }

    order_id = await db.save_order(message.from_user.id, order_data)

    admin_message = await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=f"💳 **Скріншот оплати від @{message.from_user.username} для замовлення #{order_id}**",
        reply_markup=kb.payment_approval_buttons(message.from_user.id, order_id)
    )
    await db.save_order_admin_message_id(order_id, admin_message.message_id)

    await message.answer("✅ Дякуємо за оплату! Ваш платіж зараз проходить перевірку. Після підтвердження Ви отримаєте сповіщення про статус обробки замовлення в боті.")
    await state.clear()


# Обработка скриншота репоста
@dp.message(DiscountStates.waiting_for_repost_screenshot, F.content_type == ContentType.PHOTO)
async def receive_repost_screenshot(message: Message, state: FSMContext):
    admin_message = await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=f"🔄 **Репост від @{message.from_user.username}**",
        reply_markup=kb.approval_buttons('repost', message.from_user.id)
    )
    await db.save_discount_admin_message_id(message.from_user.id, 'repost', admin_message.message_id)

    await message.answer("✅ Дякуємо! Ваш скріншот відправлено на перевірку.")
    await state.clear()


# Обработка скриншота УБД
@dp.message(DiscountStates.waiting_for_ubd_photo, F.content_type == ContentType.PHOTO)
async def receive_ubd_photo(message: Message, state: FSMContext):
    admin_message = await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=f"🆔 **УБД від @{message.from_user.username}**",
        reply_markup=kb.approval_buttons('ubd', message.from_user.id)
    )
    await db.save_discount_admin_message_id(message.from_user.id, 'ubd', admin_message.message_id)

    await message.answer("✅ Дякуємо! Ваше зображення відправлено на перевірку.")
    await state.clear()


# Обработка нажатия администратором на кнопки одобрения или отклонения скидок
@dp.callback_query(F.data.startswith('approve_') & ~F.data.startswith('approve_payment_'))
async def admin_approve_discount(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split('_')
    discount_type = data[1]
    user_id = int(data[2])

    try:
        user_chat = await bot.get_chat(user_id)
        user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
    except Exception:
        user_username = f"User ID: {user_id}"

    # Сохраняем скидку в БД
    await db.add_discount(user_id, discount_type)

    # Отправляем уведомление администратору
    try:
        await bot.send_message(ADMIN_ID,
                               f"✅ Ви підтвердили знижку '{discount_type.upper()}' для користувача {user_username}.")
    except Exception as e:
        logger.error(f"Error sending message to admin: {e}")

    # Отправляем уведомление пользователю
    try:
        await bot.send_message(user_id, f"✅ Ваша знижка '{discount_type.upper()}' була успішно активована!")
    except Exception as e:
        logger.error(f"Error sending discount approval message to user {user_id}: {e}")

    # Удаляем inline-клавиатуру из сообщения
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"Error updating reply_markup: {e}")

    await callback.answer("Схвалено")


@dp.callback_query(F.data.startswith('reject_') & ~F.data.startswith('reject_payment_'))
async def admin_reject_discount(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    parts = data.split('_')
    discount_type = parts[1]
    user_id = int(parts[2])

    await state.update_data(discount_type=discount_type, user_id=user_id, admin_message_id=callback.message.message_id)
    await callback.message.answer("❌ Введіть причину відхилення знижки:")
    await state.set_state(AdminInputStates.order_rejection_reason)

    await callback.answer()


# Обработка ввода причины отказа для скидок
@dp.message(AdminInputStates.order_rejection_reason)
async def process_discount_rejection_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    if not reason:
        await message.answer("❌ Причина відхилення не може бути порожньою. Будь ласка, введіть причину.")
        return

    data = await state.get_data()
    discount_type = data.get('discount_type')
    user_id = data.get('user_id')
    admin_message_id = data.get('admin_message_id')

    if discount_type not in {'ubd', 'repost'}:
        await message.answer("❌ Невідома тип знижки.")
        await state.clear()
        return

    await db.remove_discount(user_id, discount_type)
    await db.save_discount_rejection_reason(user_id, discount_type, reason)

    try:
        user_chat = await bot.get_chat(user_id)
        user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
    except Exception:
        user_username = f"User ID: {user_id}"

    reject_text = f"❌ Ваша знижка '{discount_type.upper()}' була відхилена.\nПричина: {reason}"
    try:
        await bot.send_message(user_id, reject_text)
    except Exception as e:
        logger.error(f"Error sending discount rejection message to user {user_id}: {e}")

    try:
        admin_message = await bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            caption=f"{callback.message.caption}\n\n❌ Знижку '{discount_type.upper()}' для користувача {user_username} відхилено.\n📝 Причина: {reason}"
        )
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Error updating admin message with rejection reason: {e}")

    await message.answer("✅ Причина відхилення збережена та користувачу надіслано повідомлення.")
    await state.clear()


# Обработка нажатия администратором на кнопки одобрения или отклонения оплаты
@dp.callback_query(F.data.startswith('approve_payment_'))
async def admin_approve_payment(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split('_')
    user_id = int(data[2])
    order_id = int(data[3])

    try:
        user_chat = await bot.get_chat(user_id)
        user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
    except Exception:
        user_username = f"User ID: {user_id}"

    # Обновляем статус заказа в базе
    await db.update_order_status(order_id, 'Оплачено')

    # Уведомляем пользователя!!
    try:
        await bot.send_message(user_id, f"✅ Ваше замовлення #{order_id} було підтверджено та оброблено.")
    except Exception as e:
        logger.error(f"Error sending payment approval message to user {user_id}: {e}")

    # Удаляем inline-клавиатуру из сообщения
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"Error updating reply_markup: {e}")

    # Обновляем информацию для администратора – отправляем новое сообщение с меню обработки заказа
    try:
        await process_order_for_admin(order_id, user_username, user_id)
    except Exception as e:
        logger.error(f"Error processing order for admin: {e}")

    await callback.answer("Оплату підтверджено")


@dp.callback_query(F.data.startswith('reject_payment_'))
async def admin_reject_payment(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    parts = data.split('_')
    user_id = int(parts[2])
    order_id = int(parts[3])

    await state.update_data(order_id=order_id, user_id=user_id, admin_message_id=callback.message.message_id)
    await callback.message.answer("❌ Введіть причину відхилення оплати:")
    await state.set_state(AdminInputStates.payment_rejection_reason)

    await callback.answer()


# Обработка ввода причины отказа для оплаты
@dp.message(AdminInputStates.payment_rejection_reason)
async def process_payment_rejection_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    if not reason:
        await message.answer("❌ Причина відхилення не може бути порожньою. Будь ласка, введіть причину.")
        return

    data = await state.get_data()
    order_id = data.get('order_id')
    user_id = data.get('user_id')
    admin_message_id = data.get('admin_message_id')

    if not order_id or not user_id:
        await message.answer("❌ Невірні дані замовлення.")
        await state.clear()
        return

    await db.update_order_status(order_id, 'Оплата відхилена')
    await db.save_order_rejection_reason(order_id, reason)

    try:
        user_chat = await bot.get_chat(user_id)
        user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
    except Exception:
        user_username = f"User ID: {user_id}"

    reject_text = f"❌ Оплата за ваше замовлення #{order_id} була відхилена.\nПричина: {reason}"
    try:
        await bot.send_message(user_id, reject_text)
    except Exception as e:
        logger.error(f"Error sending payment rejection message to user {user_id}: {e}")

    try:
        admin_message = await bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            caption=f"{callback.message.caption}\n\n❌ Оплату за замовлення #{order_id} відхилено.\n📝 Причина: {reason}"
        )
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Error updating admin message with rejection reason: {e}")

    await message.answer("✅ Причина відхилення оплати збережена та користувачу надіслано повідомлення.")
    await state.clear()


# Функция расчёта цены
async def calculate_price(product, user_id):
    base_price = 1150 if product.get('model_id', '').startswith('ts') else 1350
    total_discount = 0.0
    discounts = await db.get_user_discounts(user_id)
    discount_details = []

    if discounts.get('ubd'):
        total_discount += 0.10
        discount_details.append('🎖️ 10% за УБД')
    if discounts.get('repost'):
        total_discount += 0.10
        discount_details.append('🔄 10% за репост')

    final_price = base_price * (1 - total_discount)
    final_price = int(final_price)

    if discount_details:
        discount_text = f"🎁 **Ваша знижка:** {' + '.join(discount_details)}"
    else:
        discount_text = "🎁 **Знижки не застосовано**"

    return final_price, discount_text


# Функция форматирования текста заказа для админа и пользователя
async def format_order_text(order, order_id, username, user_id):
    product_code = order.get('product')
    product = 'Футболка' if product_code.startswith('ts') else 'Худі'
    size = order.get('size', 'Не обрано')

    discounts = await db.get_user_discounts(user_id)
    discounts_text = []
    if discounts.get('ubd'):
        discounts_text.append('🎖️ УБД - 10%')
    if discounts.get('repost'):
        discounts_text.append('🔄 Репост - 10%')
    discounts_str = ', '.join(discounts_text) if discounts_text else '❌ Немає'

    price = order.get('price', 'Не вказано')

    options_text = ""
    if product == 'Футболка':
        if order.get('made_in_ukraine'):
            options_text += "✅ Made in Ukraine принт\n"
        if order.get('back_text'):
            options_text += "✅ Задній підпис\n"
        if order.get('back_print'):
            options_text += "✅ Задній принт\n"
    elif product == 'Худі':
        if order.get('sleeve_text'):
            options_text += "✅ Принт на рукавах\n"

    if options_text:
        options_text = "\n**Вибрані опції:**\n" + options_text
    else:
        options_text = "\n**Вибрані опції:**\n❌ Немає"

    rejection_reason_text = ""
    if order.get('rejection_reason'):
        rejection_reason_text = f"\n❌ **Причина відхилення:** {order.get('rejection_reason')}"

    ttn_text = ""
    if order.get('ttn'):
        ttn_text = f"\n📦 **ТТН:** {order.get('ttn')}"

    text = (
        f"📝 **Замовлення #{order_id}**\n"
        f"🛍️ **Товар:** {product}\n"
        f"📏 **Розмір:** {size}\n"
        f"🏙️ **Місто:** {order.get('city')}\n"
        f"🏢 **Відділення:** {order.get('branch')}\n"
        f"🧑 **ПІБ:** {order.get('name')}\n"
        f"📞 **Телефон:** {order.get('phone')}\n"
        f"💳 **Спосіб оплати:** {'💳 Оплата на карту' if order.get('payment_method') == 'card' else '💰 Плата на пошті'}\n"
        f"🎖️ **Знижки:** {discounts_str}\n"
        f"💸 **Сума до оплати:** {price} грн"
        f"{options_text}"
        f"{rejection_reason_text}"
        f"{ttn_text}"
    )
    return text


# Функция для получения статусов кнопок на основе статуса заказа
def get_statuses_from_order_status(order_status):
    statuses = {
        'ready': False,
        'sent': False,
        'delivered': False
    }
    if order_status in ['Нове', 'Оплата підтверджена', 'Очікується підтвердження оплати', 'Оплачено']:
        statuses['ready'] = False
    elif order_status == 'Готово до відправки':
        statuses['ready'] = True
    elif order_status == 'Відправлено':
        statuses['ready'] = True
        statuses['sent'] = True
    elif order_status == 'Доставлено':
        statuses['ready'] = True
        statuses['sent'] = True
        statuses['delivered'] = True
    return statuses


# Функция для получения URL изображения заказа
async def get_order_image_url(order):
    if not os.path.exists(PRODUCTS_JSON_PATH):
        return "https://i.ibb.co/cx351Lx/1-2.png"

    with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
        products = json.load(f)
    category = 't_shirts' if order['product'].startswith('ts') else 'hoodies'
    category_products = products.get(category, [])
    product_data = next((p for p in category_products if p['model_id'] == order['product']), None)
    if not product_data:
        image_url = "https://i.ibb.co/cx351Lx/1-2.png"
    else:
        selected_color_index = order.get('selected_color_index', 0)
        colors = product_data['colors']
        if colors:
            image_url = colors[selected_color_index % len(colors)]
        else:
            image_url = "https://i.ibb.co/cx351Lx/1-2.png"
    return image_url


# Обработка раздела "🔥 Мої акції та знижки"
@dp.message(F.text == '🔥 Мої акції та знижки')
async def my_promotions(message: Message):
    discounts = await db.get_user_discounts(message.from_user.id)
    discount_texts = []
    if discounts.get('ubd'):
        discount_texts.append('🎖️ 10% за УБД')
    if discounts.get('repost'):
        discount_texts.append('🔄 10% за репост')
    discounts_str = ', '.join(discount_texts) if discount_texts else '❌ Немає'

    one_time_discount_used = await db.is_one_time_discount_used(message.from_user.id)
    if discounts.get('repost') and one_time_discount_used:
        discounts_str += "\n❗️ Знижку за репост вже було використано."
    elif not discounts.get('repost') and one_time_discount_used:
        discounts_str += "\n❗️ Знижку за репост вже було використано."

    keyboard_buttons = []
    if not discounts.get('ubd'):
        keyboard_buttons.append([KeyboardButton(text='📷 Показати УБД')])
    if not discounts.get('repost') and not one_time_discount_used:
        keyboard_buttons.append([KeyboardButton(text='🔗 Показати скрін репосту')])
    keyboard_buttons.append([KeyboardButton(text='🔙 На головну')])
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)

    await message.answer(
        f"🎁 **Спеціальна пропозиція!**\n\n"
        f"Отримайте знижку **10%** для військовослужбовців та додаткові **10%** при репості нашого посту в Instagram!\n\n"
        f"🔹 **Активовані знижки:** {discounts_str}",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# Обработка кнопки "📷 Показати УБД"
@dp.message(F.text == '📷 Показати УБД')
async def send_ubd(message: Message, state: FSMContext):
    await message.answer("📷 Будь ласка, надішліть фото вашого УБД.")
    await state.set_state(DiscountStates.waiting_for_ubd_photo)


# Обработка кнопки "🔗 Показати скрін репосту"
@dp.message(F.text == '🔗 Показати скрін репосту')
async def send_repost(message: Message, state: FSMContext):
    await message.answer("📸 Будь ласка, надішліть скріншот репосту з Instagram.")
    await state.set_state(DiscountStates.waiting_for_repost_screenshot)


# Обработка кнопки "💬 Інформація та підтримка"
@dp.message(F.text == '💬 Інформація та підтримка')
async def info_support(message: Message):
    await message.answer(
        'Оберіть опцію:',
        reply_markup=kb.info_support_buttons()
    )


# Обработка кнопки "📞 Зв'язатися з підтримкою"
@dp.message(F.text == '📞 Зв\'язатися з підтримкою')
async def contact_support(message: Message, state: FSMContext):
    await message.answer("Будь ласка, опишіть вашу проблему або питання.")
    await state.set_state(SupportStates.waiting_for_issue_description)


# Обработка ввода описания проблемы от пользователя
@dp.message(SupportStates.waiting_for_issue_description)
async def receive_issue_description(message: Message, state: FSMContext):
    issue_text = message.text.strip()
    if not issue_text:
        await message.answer("❌ Будь ласка, опишіть вашу проблему більш детально.")
        return

    issue_id = await db.save_user_issue(message.from_user.id, issue_text)

    await bot.send_message(
        ADMIN_ID,
        f"📩 **Нове повідомлення в підтримку від @{message.from_user.username}:**\n\n{issue_text}",
        reply_markup=kb.admin_support_reply_button(issue_id)
    )

    await message.answer(
        "✅ Ваше повідомлення надіслано в підтримку. Ми зв'яжемося з вами найближчим часом.",
        reply_markup=kb.back_to_main_menu()
    )
    await state.clear()


# Обработка нажатия администратором на кнопку "✉️ Відповісти" в сообщении поддержки
@dp.callback_query(F.data.startswith('support_reply_'))
async def admin_support_reply(callback: CallbackQuery, state: FSMContext):
    issue_id = int(callback.data.split('_')[-1])
    await state.update_data(issue_id=issue_id)
    await callback.message.answer("✏️ Введіть вашу відповідь користувачу:")
    await state.set_state(AdminInputStates.admin_support_reply)
    await callback.answer()


# Обработка ввода ответа от администратора
@dp.message(AdminInputStates.admin_support_reply)
async def admin_support_send_reply(message: Message, state: FSMContext):
    reply_text = message.text.strip()
    if not reply_text:
        await message.answer("❌ Відповідь не може бути порожньою.")
        return

    data = await state.get_data()
    issue_id = data.get('issue_id')
    issue = await db.get_user_issue(issue_id)
    if not issue:
        await message.answer("❌ Не вдалося знайти звернення користувача.")
        await state.clear()
        return

    user_id = issue['user_id']
    await bot.send_message(
        user_id,
        f"📩 **Відповідь від підтримки:**\n\n{reply_text}",
        reply_markup=kb.support_response_options()
    )
    await message.answer("✅ Відповідь надіслано користувачу.")
    await state.clear()


# Обработка кнопок ответа пользователя после получения ответа от поддержки
@dp.callback_query(F.data.in_(['support_resolved', 'support_more_question']))
async def user_support_response(callback: CallbackQuery, state: FSMContext):
    if callback.data == 'support_resolved':
        await callback.message.answer("😊 Дякуємо за звернення! Якщо у вас будуть ще питання, звертайтеся.")
        await state.clear()
    elif callback.data == 'support_more_question':
        await callback.message.answer("Будь ласка, опишіть вашу проблему або питання.")
        await state.set_state(SupportStates.waiting_for_issue_description)
    await callback.answer()


# Обработка кнопки "ℹ️ Інформація про бренд"
@dp.message(F.text == 'ℹ️ Інформація про бренд')
async def brand_info(message: Message):
    await message.answer(
        'Наш бренд займається виготовленням якісного одягу з унікальними принтами. Ми цінуємо кожного клієнта та намагаємось зробити наш сервіс максимально зручним для вас.',
        reply_markup=kb.back_to_main_menu()
    )


# Обработка кнопки "🖼️ Запропонувати принт"
@dp.message(F.text == '🖼️ Запропонувати принт')
async def propose_print(message: Message, state: FSMContext):
    await message.answer("📷 Будь ласка, надішліть зображення вашого принта.")
    await state.set_state(AdminInputStates.waiting_for_print_description)
    await state.update_data(propose_print=True)


# Обработка получения изображения принта от пользователя
@dp.message(AdminInputStates.waiting_for_print_description, F.content_type == ContentType.PHOTO)
async def receive_print_image(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get('propose_print'):
        await bot.send_photo(
            ADMIN_ID,
            message.photo[-1].file_id,
            caption=f"🎨 **Новий принт від @{message.from_user.username}**",
        )
        await message.answer("✅ Дякуємо! Ваш принт було відправлено на розгляд.")
        await state.clear()
    else:
        pass


# Обработка кнопки "🤝 Співробітництво"
@dp.message(F.text == '🤝 Співробітництво')
async def cooperation(message: Message):
    await message.answer(
        'Якщо ви зацікавлені у співробітництві, будь ласка, зв\'яжіться з нами за адресою: @zainllw0w',
        reply_markup=kb.back_to_main_menu()
    )


# Обработка раздела "📋 Замовлення" для администратора
@dp.message(F.text == '📋 Замовлення')
async def admin_orders(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            'Оберіть опцію:',
            reply_markup=kb.admin_orders_menu()
        )


# Обработка кнопки "📂 Замовлення в обробці"
@dp.message(F.text == '📂 Замовлення в обробці')
async def processing_orders(message: Message):
    if message.from_user.id == ADMIN_ID:
        orders = await db.get_orders_not_delivered()
        if not orders:
            await message.answer('Немає замовлень в обробці.', reply_markup=kb.admin_main_menu())
            return

        for order in orders:
            order_text = await format_order_text(order, order['id'], '', order['user_id'])
            statuses = get_statuses_from_order_status(order['status'])
            image_url = await get_order_image_url(order)
            user_username = ''
            try:
                user_chat = await bot.get_chat(order['user_id'])
                user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
            except Exception:
                user_username = f"User ID: {order['user_id']}"
            admin_message = await bot.send_photo(
                message.from_user.id,
                photo=image_url,
                caption=f"📦 Замовлення #{order['id']} від {user_username}:\n{order_text}",
                reply_markup=kb.admin_order_actions(order['id'], statuses=statuses)
            )
            await db.save_order_admin_message_id(order['id'], admin_message.message_id)


# Обработка кнопки "📂 Виконані замовлення"
@dp.message(F.text == '📂 Виконані замовлення')
async def completed_orders(message: Message):
    if message.from_user.id == ADMIN_ID:
        orders = await db.get_orders_by_status('Доставлено')
        if not orders:
            await message.answer('Немає виконаних замовлень.', reply_markup=kb.admin_main_menu())
            return

        for order in orders:
            order_text = await format_order_text(order, order['id'], '', order['user_id'])
            image_url = await get_order_image_url(order)
            user_username = ''
            try:
                user_chat = await bot.get_chat(order['user_id'])
                user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
            except Exception:
                user_username = f"User ID: {order['user_id']}"
            await bot.send_photo(
                message.from_user.id,
                photo=image_url,
                caption=f"✅ Виконане замовлення #{order['id']} від {user_username}:\n{order_text}",
                reply_markup=None
            )


@dp.callback_query(F.data.startswith('order_'))
async def admin_order_action(callback: CallbackQuery, state: FSMContext):
    """
    Общий обработчик админских кнопок вида:
     - order_ready_{id}
     - order_sent_{id}
     - order_details_{id}
     - order_create_ttn_{id}
    """
    data = callback.data
    parts = data.split('_')
    # Примеры:
    #  - "order_ready_7" => parts = ["order", "ready", "7"]
    #  - "order_sent_7" => parts = ["order", "sent", "7"]
    #  - "order_details_7" => parts = ["order", "details", "7"]
    #  - "order_create_ttn_7" => parts = ["order", "create", "ttn", "7"]

    if len(parts) < 3:
        await callback.answer('Невідома дія.')
        return

    main_action = parts[1]  # "ready" / "sent" / "details" / "create" и т.п.

    # --------------------------
    # 1) ОБРАБОТКА "order_create_ttn_{id}"
    # --------------------------
    if main_action == "create":
        # Значит у нас нечто вроде "order_create_ttn_10"
        if len(parts) < 4:
            await callback.answer("Невідома дія.")
            return

        sub_action = parts[2]  # должно быть "ttn"
        if sub_action != "ttn":
            await callback.answer("Невідома піддія створення.")
            return

        try:
            order_id = int(parts[3])
        except ValueError:
            await callback.answer("Невірний формат order_id.")
            return

        # Ищем заказ в БД
        order = await db.get_order_by_id(order_id)
        if not order:
            await callback.answer('Замовлення не знайдено.')
            return

        # Переход к FSM AdminTtnFlow:
        #  1) сохраним order_id в state
        #  2) спросим у админа город отправителя (Киев/Харьков)
        await state.update_data(order_id=order_id)
        await state.set_state(AdminTtnFlow.waiting_for_city)

        # Выведем кнопки выбора города
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text='Київ', callback_data='sender_city_kyiv'),
                InlineKeyboardButton(text='Харків', callback_data='sender_city_kharkiv')
            ]
        ])
        await callback.message.answer(
            "Оберіть місто відправлення:",
            reply_markup=keyboard
        )
        await callback.answer()
        return

    # --------------------------
    # 2) ОБРАБОТКА "order_ready_{id}", "order_sent_{id}", "order_delivered_{id}",
    #    "order_cancel_{id}", "order_details_{id}"
    # --------------------------
    # если main_action != "create", значит обычные действия.
    try:
        order_id = int(parts[2])  # берем order_id из parts[2]
    except ValueError:
        await callback.answer("Невірний ID замовлення.")
        return

    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.answer('Замовлення не знайдено.')
        return

    user_id = order['user_id']
    admin_message_id = order.get('admin_message_id')

    if main_action == 'ready':
        await db.update_order_status(order_id, 'Готово до відправки')
        await bot.send_message(user_id, f"Ваше замовлення #{order_id} готове до відправки.")

    elif main_action == 'sent':
        # Старая логика: запрос номера ТТН вручную
        await callback.message.answer("📦 Введіть номер ТТН для замовлення:")
        await state.update_data(order_id=order_id, user_id=user_id)
        await state.set_state(AdminInputStates.waiting_for_ttn)
        await callback.answer()
        return

    elif main_action == 'delivered':
        await db.update_order_status(order_id, 'Доставлено')
        await bot.send_message(user_id, f"Ваше замовлення #{order_id} доставлено. Дякуємо за покупку!")

    elif main_action == 'cancel':
        await db.update_order_status(order_id, 'Відхилено')
        await bot.send_message(user_id, f"Ваше замовлення #{order_id} було відхилено.")

    elif main_action == 'details':
        local_status = order.get('status', 'Невідомий')
        ttn = order.get('ttn')
        order_text = await format_order_text(
            order,
            order_id,
            callback.from_user.username,
            callback.from_user.id
        )
        if not ttn:
            message_text = (
                f"{order_text}\n\n"
                f"Статус (з БД): {local_status}\n"
                f"TTN: Немає\n"
            )
        else:
            np_status = await get_nova_poshta_status(ttn)  # ваша функция трекинга
            message_text = (
                f"{order_text}\n\n"
                f"📦 **Статус НП**: {np_status}\n"
                f"TTN: {ttn}"
            )
        await callback.message.answer(message_text, parse_mode='Markdown')
    else:
        await callback.answer('Невідома дія.')
        return

    # --------------------------
    # 3) Завершаем обработку: обновляем inline-клавиатуру для админа (если нужно)
    # --------------------------
    # Перечитываем заказ, чтобы обновить статус (если он поменялся)
    order = await db.get_order_by_id(order_id)
    statuses = get_statuses_from_order_status(order['status'])
    try:
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            reply_markup=kb.admin_order_actions(order_id, statuses=statuses)
        )
    except Exception as e:
        logger.error(f"Error updating admin message: {e}")

    await callback.answer('Статус замовлення оновлено.')




# Обработка ввода ТТН от администратора
@dp.message(AdminInputStates.waiting_for_ttn)
async def admin_receive_ttn(message: Message, state: FSMContext):
    ttn = message.text.strip()
    data = await state.get_data()
    order_id = data.get('order_id')
    user_id = data.get('user_id')

    if not ttn:
        await message.answer("❌ Номер ТТН не може бути порожнім.")
        return

    await db.update_order_ttn(order_id, ttn)
    await db.update_order_status(order_id, 'Відправлено')
    await bot.send_message(user_id, f"Ваше замовлення #{order_id} відправлено.\nНомер ТТН: {ttn}")

    order = await db.get_order_by_id(order_id)
    statuses = get_statuses_from_order_status(order['status'])
    await message.reply("✅ ТТН збережено та відправлено користувачу.")
    await state.clear()

    admin_message_id = order.get('admin_message_id')
    try:
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            reply_markup=kb.admin_order_actions(order_id, statuses=statuses)
        )
    except Exception as e:
        logger.error(f"Error updating admin message: {e}")


# Запуск бота
async def main():
    await db.init_db()
    await dp.start_polling(bot, on_startup=on_startup)


# Фоновая задача для обновления продуктов
async def background_task():
    while True:
        fetch_and_update_products()
        await asyncio.sleep(1200)


async def on_startup(dp: Dispatcher):
    asyncio.create_task(background_task())
    logger.info(f"[{datetime.now()}] Фоновая задача для оновлення продуктів запущена.")


# Функция для поддержания работы бота на некоторых хостингах (например, Replit)
from flask import Flask
from threading import Thread

app_flask = Flask(__name__)


@app_flask.route('/')
def home():
    return "Бот працює!"


def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)


def start_flask():
    thread = Thread(target=run_flask)
    thread.start()


# 1. Обработка кнопки "Як відбувається доставка"
@dp.callback_query(F.data == 'how_delivery')
async def how_delivery_handler(callback: CallbackQuery):
    text = (
        "🚚 **Доставка**\n\n"
        "Ваше замовлення буде відправлено Новою Поштою.\n"
        "Оплатити можна як накладеним платежем безпосередньо у відділенні, "
        "так і на карту – у цьому випадку доставка також здійснюється Новою Поштою.\n\n"
        "Якщо оплата буде здійснена відразу на карту, доставка для Вас – безкоштовна."
    )
    await callback.message.answer(text, parse_mode='Markdown')
    await callback.answer()


# ======================================================================
# 2. Унификация обработки заказа при оплате на карту

async def process_order_for_admin(order_id, user_username, user_id):
    order = await db.get_order_by_id(order_id)
    order_text = await format_order_text(order, order_id, user_username, user_id)
    statuses = get_statuses_from_order_status(order['status'])
    image_url = await get_order_image_url(order)
    admin_message = await bot.send_photo(
        ADMIN_ID,
        photo=image_url,
        caption=f"📦 **Замовлення #{order_id}** від {user_username}:\n{order_text}",
        reply_markup=kb.admin_order_actions(order_id, statuses=statuses)
    )
    await db.save_order_admin_message_id(order_id, admin_message.message_id)


@dp.callback_query(F.data.startswith('approve_payment_'))
async def admin_approve_payment(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split('_')
    user_id = int(data[2])
    order_id = int(data[3])
    try:
        user_chat = await bot.get_chat(user_id)
        user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
    except Exception:
        user_username = f"User ID: {user_id}"

    await db.update_order_status(order_id, 'Оплачено')
    try:
        await bot.send_message(user_id, f"✅ Ваше замовлення #{order_id} було підтверджено та оброблено.")
    except Exception as e:
        logger.error(f"Error sending payment approval message to user {user_id}: {e}")

    new_caption = f"{callback.message.caption}\n\n✅ Оплату підтверджено для замовлення #{order_id}."
    try:
        await callback.message.edit_caption(new_caption)
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"Error updating reply_markup: {e}")

    await process_order_for_admin(order_id, user_username, user_id)
    await callback.answer()


# ======================================================================
# 3. Уведомления при подтверждении скидок

@dp.callback_query(F.data.startswith('approve_') & ~F.data.startswith('approve_payment_'))
async def admin_approve_discount(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split('_')
    discount_type = data[1]
    user_id = int(data[2])
    try:
        user_chat = await bot.get_chat(user_id)
        user_username = f"@{user_chat.username}" if user_chat.username else user_chat.full_name
    except Exception:
        user_username = f"User ID: {user_id}"

    await db.add_discount(user_id, discount_type)

    # Отправляем уведомления и администратору, и пользователю
    await bot.send_message(ADMIN_ID,
                           f"✅ Ви підтвердили знижку '{discount_type.upper()}' для користувача {user_username}.")
    try:
        await bot.send_message(user_id, f"✅ Ваша знижка '{discount_type.upper()}' була успішно активована!")
    except Exception as e:
        logger.error(f"Error sending discount approval message to user {user_id}: {e}")

    new_caption = f"{callback.message.caption}\n\n✅ Знижку '{discount_type.upper()}' для користувача {user_username} схвалено."
    try:
        await callback.message.edit_caption(new_caption)
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"Error updating reply_markup: {e}")

    await callback.answer()


# ======================================================================
# Вспомогательные функции (расчет цены, форматирование заказа, получение статусов и URL изображения)

async def calculate_price(product, user_id):
    base_price = 1150 if product.get('model_id', '').startswith('ts') else 1350
    total_discount = 0.0
    discounts = await db.get_user_discounts(user_id)
    discount_details = []
    if discounts.get('ubd'):
        total_discount += 0.10
        discount_details.append('🎖️ 10% за УБД')
    if discounts.get('repost'):
        total_discount += 0.10
        discount_details.append('🔄 10% за репост')
    final_price = int(base_price * (1 - total_discount))
    discount_text = (f"🎁 **Ваша знижка:** {' + '.join(discount_details)}"
                     if discount_details else "🎁 **Знижки не застосовано**")
    return final_price, discount_text


async def format_order_text(order, order_id, username, user_id):
    product_code = order.get('product')
    product = 'Футболка' if product_code.startswith('ts') else 'Худі'
    size = order.get('size', 'Не обрано')
    discounts = await db.get_user_discounts(user_id)
    discounts_text = []
    if discounts.get('ubd'):
        discounts_text.append('🎖️ УБД - 10%')
    if discounts.get('repost'):
        discounts_text.append('🔄 Репост - 10%')
    discounts_str = ', '.join(discounts_text) if discounts_text else '❌ Немає'
    price = order.get('price', 'Не вказано')
    options_text = ""
    if product == 'Футболка':
        if order.get('made_in_ukraine'):
            options_text += "✅ Made in Ukraine принт\n"
        if order.get('back_text'):
            options_text += "✅ Задній підпис\n"
        if order.get('back_print'):
            options_text += "✅ Задній принт\n"
    elif product == 'Худі':
        if order.get('collar'):
            options_text += "✅ Горловина\n"
        if order.get('sleeve_text'):
            options_text += "✅ Надписи на рукавах\n"
        if order.get('back_print'):
            options_text += "✅ Задній принт\n"
    options_text = "\n**Вибрані опції:**\n" + options_text if options_text else "\n**Вибрані опції:**\n❌ Немає"
    rejection_reason_text = f"\n❌ **Причина відхилення:** {order.get('rejection_reason')}" if order.get(
        'rejection_reason') else ""
    ttn_text = f"\n📦 **ТТН:** {order.get('ttn')}" if order.get('ttn') else ""
    text = (
        f"📝 **Замовлення #{order_id}**\n"
        f"🛍️ **Товар:** {product}\n"
        f"📏 **Розмір:** {size}\n"
        f"🏙️ **Місто:** {order.get('city')}\n"
        f"🏢 **Відділення:** {order.get('branch')}\n"
        f"🧑 **ПІБ:** {order.get('name')}\n"
        f"📞 **Телефон:** {order.get('phone')}\n"
        f"💳 **Спосіб оплати:** {'💳 Оплата на карту' if order.get('payment_method') == 'card' else '💰 Плата на пошті'}\n"
        f"🎖️ **Знижки:** {discounts_str}\n"
        f"💸 **Сума до оплати:** {price} грн"
        f"{options_text}"
        f"{rejection_reason_text}"
        f"{ttn_text}"
    )
    return text


def get_statuses_from_order_status(order_status):
    statuses = {'ready': False, 'sent': False, 'delivered': False}
    if order_status in ['Нове', 'Оплата підтверджена', 'Очікується підтвердження оплати', 'Оплачено']:
        statuses['ready'] = False
    elif order_status == 'Готово до відправки':
        statuses['ready'] = True
    elif order_status == 'Відправлено':
        statuses['ready'] = True
        statuses['sent'] = True
    elif order_status == 'Доставлено':
        statuses['ready'] = True
        statuses['sent'] = True
        statuses['delivered'] = True
    return statuses


async def get_order_image_url(order):
    if not os.path.exists(PRODUCTS_JSON_PATH):
        return "https://i.ibb.co/cx351Lx/1-2.png"
    with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
        products = json.load(f)
    category = 't_shirts' if order['product'].startswith('ts') else 'hoodies'
    category_products = products.get(category, [])
    product_data = next((p for p in category_products if p['model_id'] == order['product']), None)
    if product_data:
        colors = product_data.get('colors', [])
        index = order.get('selected_color_index', 0)
        if colors and 0 <= index < len(colors):
            return colors[index]
    return "https://i.ibb.co/cx351Lx/1-2.png"

NOVA_POSHTA_API_KEY = os.environ.get("NOVA_POSHTA_API_KEY")

async def get_nova_poshta_status(ttn: str) -> str:
    """
    Делает запрос к API Новой Почты, возвращает строку со статусом посылки.
    Если не удалось получить статус — возвращает текст об ошибке.
    """
    url = "https://api.novaposhta.ua/v2.0/json/"
    payload = {
        "apiKey": NOVA_POSHTA_API_KEY,
        "modelName": "TrackingDocument",
        "calledMethod": "getStatusDocuments",
        "methodProperties": {
            "Documents": [
                {
                    "DocumentNumber": ttn,
                    "Phone": ""  # Можно указать телефон, если хотите
                }
            ]
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                # Ожидаем, что data['data'] — список документов
                doc_info = data.get('data', [])
                if not doc_info:
                    return "Не вдалося отримати дані від Нової Пошти."
                doc = doc_info[0]
                # Из doc можно достать много полей:
                #   Status, StatusCode, WarehouseRecipientAddress, DeliveryDate, RecipientDateTime и т.д.
                return doc.get('Status', 'Статус невідомий')
    except Exception as e:
        return f"Помилка з'єднання з Новою Поштою: {e}"


@dp.callback_query(F.data.startswith('order_details_'))
async def order_details_callback(callback: CallbackQuery, state: FSMContext):
    # Парсим order_id из строки "order_details_123"
    parts = callback.data.split('_')
    # parts[0] = "order", parts[1] = "details", parts[2] = "{order_id}"
    order_id = int(parts[2])

    # Получаем заказ из БД по ID
    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.answer("Замовлення не знайдено.", show_alert=True)
        return

    # Если TTN нет -> выводим локальный статус, если есть -> запрашиваем НП
    ttn = order.get('ttn')
    local_status = order.get('status', 'Невідомий')

    # Можно использовать вашу функцию format_order_text для подробностей
    order_text = await format_order_text(order, order_id, callback.from_user.username, callback.from_user.id)

    if not ttn:
        # Показываем статус из БД и пишем, что TTN нет
        message_text = (
            f"{order_text}\n\n"
            f"Статус (з БД): {local_status}\n"
            f"TTN: Немає\n"
        )
        await callback.message.answer(message_text, parse_mode='Markdown')
    else:
        # Если TTN есть, обращаемся к API Новой Почты
        np_status = await get_nova_poshta_status(ttn)  # ваша функция запроса
        message_text = (
            f"{order_text}\n\n"
            f"📦 **Статус з Нової Пошти:** {np_status}\n"
            f"TTN: {ttn}"
        )
        await callback.message.answer(message_text, parse_mode='Markdown')

    # Обязательный ответ колбэку, чтобы Telegram не думал, что бот завис
    await callback.answer()

async def auto_check_nova_poshta():
    """
    Раз в час проверяем все заказы со статусом != 'Доставлено' и != 'Відхилено',
    у которых есть TTN. Если 'Відправлення отримано' — ставим 'Доставлено',
    пишем пользователю и админу.
    """
    while True:
        try:
            orders = await get_orders_not_delivered()  # все, у кого status != 'Доставлено' / 'Відхилено'
            for order in orders:
                order_id = order['id']
                ttn = order.get('ttn')
                if not ttn:
                    continue  # нет TTN — пропускаем

                np_status = await get_nova_poshta_status(ttn)
                if "Відправлення отримано" in np_status:
                    # 1) Ставим статус 'Доставлено'
                    await update_order_status(order_id, 'Доставлено')

                    # 2) Уведомляем пользователя
                    user_id = order['user_id']
                    user_message = (
                        f"Дякуємо, що обрали наш магазин!\n"
                        f"Ваше замовлення #{order_id} з номером ТТН {ttn} щойно було отримано "
                        f"у відділенні Нової Пошти. Бажаємо приємного користування!"
                    )
                    try:
                        await bot.send_message(user_id, user_message)
                    except Exception as e:
                        logging.error(f"Не вдалося відправити повідомлення користувачу {user_id}: {e}")

                    # 3) Уведомляем администратора
                    admin_message = (
                        f"Замовлення #{order_id} з TTN: {ttn} "
                        f"отримано користувачем і переведено в статус 'Доставлено'."
                    )
                    try:
                        await bot.send_message(ADMIN_ID, admin_message)
                    except Exception as e:
                        logging.error(f"Не вдалося відправити повідомлення адміністратору: {e}")

                    logging.info(f"Заказ #{order_id} (TTN {ttn}) переведён в 'Доставлено'")
        except Exception as e:
            logging.error(f"Ошибка в auto_check_nova_poshta: {e}")

        # Ждём 1 час и повторяем
        await asyncio.sleep(3600)

@dp.callback_query(F.data.startswith('order_create_ttn_'))
async def admin_create_ttn_start(callback: CallbackQuery, state: FSMContext):
    # Пример callback_data: "order_create_ttn_123"
    parts = callback.data.split('_')  # ["order", "create", "ttn", "123"]
    order_id = int(parts[3])

    # Сохраняем order_id во временное хранилище FSM
    await state.update_data(order_id=order_id)

    # Переходим в состояние waiting_for_city
    await state.set_state(AdminTtnFlow.waiting_for_city)

    # Предлагаем выбрать город
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Київ', callback_data='sender_city_kyiv'),
            InlineKeyboardButton(text='Харків', callback_data='sender_city_kharkiv')
        ]
    ])
    await callback.message.answer("Оберіть місто відправлення:", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(AdminTtnFlow.waiting_for_city, F.data.startswith('sender_city_'))
async def admin_choose_city(callback: CallbackQuery, state: FSMContext):
    # sender_city_kyiv или sender_city_kharkiv
    city_code = callback.data.split('_')[2]  # "kyiv" или "kharkiv"
    # Сохраним это в FSM
    await state.update_data(sender_city=city_code)

    # Теперь переходим к выбору, кто платит
    await state.set_state(AdminTtnFlow.waiting_for_payer)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Наложений платіж', callback_data='payer_cod'),
            InlineKeyboardButton(text='Я оплачую', callback_data='payer_sender')
        ]
    ])
    await callback.message.answer("Хто оплачує доставку?", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(AdminTtnFlow.waiting_for_payer, F.data.in_(['payer_cod', 'payer_sender']))
async def admin_choose_payer(callback: CallbackQuery, state: FSMContext):
    payer_type = callback.data  # "payer_cod" или "payer_sender"
    await state.update_data(payer_type=payer_type)

    # Следующий шаг - ввод номера отделения отправителя
    await callback.message.answer("Введіть номер відділення, з якого ви відправляєте (наприклад, 52).")
    await state.set_state(AdminTtnFlow.waiting_for_sender_branch)
    await callback.answer()
@dp.message(AdminTtnFlow.waiting_for_sender_branch)
async def admin_input_sender_branch(message: Message, state: FSMContext):
    branch = message.text.strip()
    # Сохраняем в FSM
    await state.update_data(sender_branch=branch)

    # + телефон/ФИО отправителя можно захардкодить в .env
    # или тоже просить вводить. Допустим, захардкодим:
    sender_phone = "+380939693920"
    sender_name = "Синіло Артем Віталійович"
    await state.update_data(sender_phone=sender_phone, sender_name=sender_name)

    # Теперь собираем сводку
    data = await state.get_data()
    order_id = data['order_id']
    order = await db.get_order_by_id(order_id)
    if not order:
        await message.answer("Замовлення не знайдено, перезапустіть процес.")
        await state.clear()
        return

    # Данные пользователя
    user_name = order['name']
    user_phone = order['phone']
    user_city = order['city']
    user_branch = order['branch']
    price = order.get('price', 0)  # сумма заказа

    # Смотрим, что выбрали
    city_code = data['sender_city']  # "kyiv" / "kharkiv"
    city_sender_name = "Київ" if city_code == "kyiv" else "Харків"
    payer_type = data['payer_type'] # "payer_cod" / "payer_sender"
    if payer_type == 'payer_cod':
        payer_str = f"Наложений платіж, сума: {price} грн"
    else:
        payer_str = "Оплачує відправник (ви)"

    # Собираем красивое сообщение
    summary = (
        "Перевірте дані для створення ТТН:\n\n"
        f"Відправник: {sender_name}\n"
        f"Телефон відправника: {sender_phone}\n"
        f"Місто відправника: {city_sender_name}\n"
        f"Відділення відправника: {branch}\n\n"

        f"Отримувач: {user_name}\n"
        f"Телефон отримувача: {user_phone}\n"
        f"Місто отримувача: {user_city}\n"
        f"Відділення отримувача: {user_branch}\n\n"

        f"Спосіб оплати: {payer_str}\n"
        f"Сума замовлення: {price} грн\n\n"
        "Підтвердити створення ТТН?"
    )
    # Выводим кнопку "Підтвердити" или "Ввести заново"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Підтвердити', callback_data='confirm_create_ttn'),
            InlineKeyboardButton(text='❌ Ввести заново', callback_data='re_enter_ttn')
        ]
    ])
    await message.answer(summary, reply_markup=keyboard)

    # Переходим в состояние waiting_for_confirm
    await state.set_state(AdminTtnFlow.waiting_for_confirm)


@dp.callback_query(AdminTtnFlow.waiting_for_confirm, F.data.in_(['confirm_create_ttn', 're_enter_ttn']))
async def admin_confirm_ttn(callback: CallbackQuery, state: FSMContext):
    if callback.data == 're_enter_ttn':
        # Вернёмся к шагу ввода отделения отправителя
        await callback.message.answer("Будь ласка, введіть номер відділення відправника заново:")
        await state.set_state(AdminTtnFlow.waiting_for_sender_branch)
        await callback.answer()
        return

    # Иначе confirm_create_ttn
    data = await state.get_data()
    order_id = data['order_id']
    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.answer("Замовлення не знайдено.", show_alert=True)
        await state.clear()
        return

    # Извлекаем всё, что нужно для формирования JSON
    sender_city_code = data['sender_city']  # "kyiv"/"kharkiv"
    # Можно сделать словарь:
    city_sender_text = "м.Київ" if sender_city_code == "kyiv" else "м.Харків"
    sender_branch = data['sender_branch']
    sender_phone = data['sender_phone']
    sender_name = data['sender_name']

    user_name = order['name']
    user_phone = order['phone']
    user_city = order['city']
    user_branch = order['branch']
    price = order.get('price', 0)

    payer_type = data['payer_type']  # "payer_cod" / "payer_sender"
    # логика наложенного платежа / кто платит
    # PayerType = 'Recipient' / 'Sender'
    # PaymentMethod = 'Cash'
    if payer_type == 'payer_cod':
        # Наложенный платёж, получатель платит
        doc_payer_type = "Recipient"
        cost = str(price)  # объявленная стоимость
        backward_delivery = True
    else:
        # Отправитель платит, оплата безнал или нал - на ваш выбор
        doc_payer_type = "Sender"
        cost = str(price)
        backward_delivery = False

    # Теперь вызываем функцию, создающую документ в Новой Почте
    # Примерно так:
    ttn, error_msg = await create_nova_poshta_document(
        user_data={
            'fullname': user_name,
            'phone': user_phone,
            'city': user_city,
            'branch': user_branch
        },
        sender_data={
            'sender_name': sender_name,
            'sender_phone': sender_phone,
            'sender_city': city_sender_text,
            'sender_branch': sender_branch
        },
        payer_type=doc_payer_type,
        cost=cost,
        backward_delivery=backward_delivery
    )
    if error_msg:
        # Если ошибка, предлагаем администратору ввести вручную
        await callback.message.answer(
            f"Помилка створення ТТН: {error_msg}\n"
            "Введіть виправлені дані отримувача вручну або спробуйте ще раз."
        )
        await state.set_state(AdminTtnFlow.waiting_for_manual_data)
        await callback.answer()
        return

    # Успешно создали ТТН => сохраняем в БД
    await db.update_order_ttn(order_id, ttn)
    # Можем обновить статус, например "Готово до відправки" или "Відправлено"
    await db.update_order_status(order_id, 'Готово до відправки')

    # Уведомляем пользователя
    user_id = order['user_id']
    await bot.send_message(
        user_id,
        f"Для вашого замовлення #{order_id} створено ТТН: {ttn}.\n"
        "Очікуйте відправлення!"
    )
    # Уведомляем администратора
    await callback.message.answer(
        f"✅ ТТН {ttn} успішно створено та додано до замовлення #{order_id}!",
    )
    await callback.answer()
    # Очистка состояния
    await state.clear()


async def create_nova_poshta_document(user_data, sender_data, payer_type, cost, backward_delivery=False):
    """
    user_data = {fullname, phone, city, branch}
    sender_data = {sender_name, sender_phone, sender_city, sender_branch}
    payer_type = 'Sender' или 'Recipient'
    cost = '500'
    backward_delivery = True/False (наложка)

    Возвращает (ttn, None) или (None, error_message)
    """
    import aiohttp

    url = "https://api.novaposhta.ua/v2.0/json/"
    payload = {
        "apiKey": NOVA_POSHTA_API_KEY,  # из .env
        "modelName": "InternetDocument",
        "calledMethod": "save",
        "methodProperties": {
            "NewAddress": "1",
            "PayerType": payer_type,       # "Recipient" / "Sender"
            "PaymentMethod": "Cash",
            "CargoType": "Cargo",
            "VolumeGeneral": "0.1",
            "Weight": "1",
            "ServiceType": "WarehouseWarehouse",
            "SeatsAmount": "1",
            "Description": "Замовлення з бота",
            "Cost": cost,  # объявленная стоимость
            "CitySender": sender_data['sender_city'],  # упрощённо: "м.Київ", но по-хорошему нужен Ref
            "SenderAddress": f"відділення {sender_data['sender_branch']}",
            "SendersPhone": sender_data['sender_phone'],
            "Sender": sender_data['sender_name'],

            "RecipientName": user_data['fullname'],
            "RecipientPhone": user_data['phone'],
            "RecipientCityName": f"м.{user_data['city']}",
            "RecipientAddressName": f"відділення №{user_data['branch']}",
            "RecipientType": "PrivatePerson"
        }
    }

    # Если наложка, указываем BackwardDeliveryData
    if backward_delivery:
        payload["methodProperties"]["BackwardDeliveryData"] = [
            {
                "PayerType": "Recipient",
                "CargoType": "Money",
                "RedeliveryString": cost
            }
        ]

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if not data.get('success'):
                errors = data.get('errors') or []
                warnings = data.get('warnings') or []
                err_msg = ', '.join(errors + warnings)
                return None, f"Помилка: {err_msg}"

            doc_info = data.get('data', [])
            if not doc_info:
                return None, "Відповідь пуста, документ не створено."

            doc = doc_info[0]
            ttn = doc.get('IntDocNumber')
            if not ttn:
                return None, "Не вдалося отримати IntDocNumber."
            return ttn, None


# ======================================================================
async def main():
    keep_alive()
    await db.init_db()  # Создаём таблицы, если их нет

    # Сначала запускаем фоновую задачу
    asyncio.create_task(auto_check_nova_poshta())
    logger.info("Фоновая задача auto_check_nova_poshta запущена.")

    # Теперь - polling (он заблокирует выполнение дальше, пока бот не остановится)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
