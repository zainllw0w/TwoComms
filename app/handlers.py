import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import os

from app import buttons as kb
from app import database as db

# Создаём бота и диспетчер
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Идентификатор администратора
ADMIN_ID = int(os.getenv('ADMIN_ID'))

# Состояния FSM для заказа
from aiogram.fsm.state import StatesGroup, State

class OrderStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_branch = State()
    waiting_for_name = State()
    waiting_for_phone = State()

class DiscountStates(StatesGroup):
    waiting_for_ubd_photo = State()
    waiting_for_repost_screenshot = State()

class SupportStates(StatesGroup):
    waiting_for_issue_description = State()

# Команда /start
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer('Вітаємо в нашому магазині! Оберіть опцію:', reply_markup=kb.main_menu())

# Обработка выбора в главном меню
@dp.message(Text('⚙️ Конструктор замовлення ⚙️'))
async def constructor_order(message: Message):
    await message.answer('Оберіть товар:', reply_markup=kb.product_selection_menu())

@dp.message(Text('На головну'))
async def back_to_main(message: Message):
    await message.answer('Повертаємось до головного меню.', reply_markup=kb.main_menu())

# Выбор футболки
@dp.message(Text('👕 - Вибрати футболку'))
async def select_tshirt(message: Message, state: FSMContext):
    await state.update_data(product='t_shirt', size=None, back_print=False, back_text=False, made_in_ukraine=False)
    await message.answer('Оберіть розмір футболки:', reply_markup=kb.t_shirtBtn)

# Выбор худі
@dp.message(Text('🥷🏼 - Вибрати худі'))
async def select_hoodie(message: Message, state: FSMContext):
    await state.update_data(product='hoodie', size=None, back_print=False, collar=False)
    await message.answer('Оберіть розмір худі:', reply_markup=kb.hoodieBtn)

# Обработка выбора размера
@dp.callback_query(Text(startswith='size_'))
async def choose_size(callback: CallbackQuery, state: FSMContext):
    size = callback.data.split('_')[1]
    await state.update_data(size=size)

    data = await state.get_data()
    text = await update_parameters(data)

    # Отображаем опции в зависимости от выбранного товара
    if data.get('product') == 't_shirt':
        await callback.message.edit_text(text=text, reply_markup=kb.generate_tshirt_option_buttons(data))
    elif data.get('product') == 'hoodie':
        await callback.message.edit_text(text=text, reply_markup=kb.generate_hoodie_option_buttons(data))
    await callback.answer()

# Обработка переключения опций
@dp.callback_query(Text(startswith='toggle_'))
async def toggle_option(callback: CallbackQuery, state: FSMContext):
    option = callback.data.split('_')[1]
    data = await state.get_data()
    current_value = data.get(option, False)
    await state.update_data(**{option: not current_value})

    data = await state.get_data()
    text = await update_parameters(data)

    if data.get('product') == 't_shirt':
        await callback.message.edit_text(text=text, reply_markup=kb.generate_tshirt_option_buttons(data))
    elif data.get('product') == 'hoodie':
        await callback.message.edit_text(text=text, reply_markup=kb.generate_hoodie_option_buttons(data))
    await callback.answer()

# Нажатие на кнопку "Продовжити"
@dp.callback_query(Text('continue'))
async def continue_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get('product')

    await send_product_photos(callback.message, product)
    await callback.answer()

# Отправка фотографий товара
async def send_product_photos(message: Message, product_type: str):
    product_photos = kb.get_product_photos(product_type)
    for photo in product_photos:
        await message.answer_photo(
            photo=photo['file_id'],
            caption=photo['caption'],
            reply_markup=kb.select_product_button()
        )

# Выбор товара
@dp.callback_query(Text('select_product'))
async def select_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = await update_parameters(data)
    await callback.message.answer(
        f"Ваше замовлення:\n{text}",
        reply_markup=kb.payment_options()
    )
    await callback.answer()

# Выбор способа оплаты
@dp.callback_query(Text('payment_post'))
async def payment_post(callback: CallbackQuery, state: FSMContext):
    await state.update_data(payment_method='post')
    await callback.message.answer("Введіть ваше місто:")
    await state.set_state(OrderStates.waiting_for_city)
    await callback.answer()

@dp.callback_query(Text('payment_card'))
async def payment_card(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    price = calculate_price(data)
    await callback.message.answer(f"Сума до оплати: {price} грн.\nНомер карти для оплати: 4441111140615463")
    await callback.message.answer("Після оплати надішліть, будь ласка, скріншот квитанції.")
    await state.set_state(OrderStates.waiting_for_payment_confirmation)
    await callback.answer()

# Сбор информации для доставки
@dp.message(OrderStates.waiting_for_city)
async def get_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Введіть номер відділення Нової Пошти:")
    await state.set_state(OrderStates.waiting_for_branch)

@dp.message(OrderStates.waiting_for_branch)
async def get_branch(message: Message, state: FSMContext):
    await state.update_data(branch=message.text)
    await message.answer("Введіть ваше ПІБ:")
    await state.set_state(OrderStates.waiting_for_name)

@dp.message(OrderStates.waiting_for_name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введіть ваш номер телефону:")
    await state.set_state(OrderStates.waiting_for_phone)

@dp.message(OrderStates.waiting_for_phone)
async def get_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    data = await state.get_data()
    # Сохраняем заказ в базу данных
    await db.save_order(data)
    await message.answer("Дякуємо! Ваше замовлення оформлено. Очікуйте підтвердження.")
    await state.clear()

# Обработка раздела "Мої акції"
@dp.message(Text('🔥 Мої акції'))
async def my_promotions(message: Message):
    await message.answer(
        "Спеціальна пропозиція!\n"
        "Отримайте знижку 10% для військовослужбовців та додаткові 10% при репості нашого посту в Instagram!\n"
        "Надішліть необхідні підтвердження для отримання знижки.",
        reply_markup=kb.discounts_menu()
    )

@dp.message(Text('Показати УБД'))
async def send_ubd(message: Message, state: FSMContext):
    await message.answer("Будь ласка, надішліть фото вашого УБД.")
    await state.set_state(DiscountStates.waiting_for_ubd_photo)

@dp.message(Text('Показати скрін репосту'))
async def send_repost(message: Message, state: FSMContext):
    await message.answer("Будь ласка, надішліть скріншот репосту з Instagram.")
    await state.set_state(DiscountStates.waiting_for_repost_screenshot)

@dp.message(DiscountStates.waiting_for_ubd_photo, content_types=ContentType.PHOTO)
async def receive_ubd_photo(message: Message, state: FSMContext):
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"УБД від @{message.from_user.username}")
    await message.answer("Дякуємо! Ваше зображення відправлено на перевірку.")
    # Сохраняем информацию о скидке в базу данных
    await db.save_discount_request(message.from_user.id, 'ubd', message.photo[-1].file_id)
    await state.clear()

@dp.message(DiscountStates.waiting_for_repost_screenshot, content_types=ContentType.PHOTO)
async def receive_repost_screenshot(message: Message, state: FSMContext):
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"Репост від @{message.from_user.username}")
    await message.answer("Дякуємо! Ваш скріншот відправлено на перевірку.")
    # Сохраняем информацию о скидке в базу данных
    await db.save_discount_request(message.from_user.id, 'repost', message.photo[-1].file_id)
    await state.clear()

# Обработка раздела "Інформація та підтримка"
@dp.message(Text('💬 Інформація та підтримка'))
async def info_support(message: Message):
    await message.answer("Оберіть опцію:", reply_markup=kb.info_support_buttons())

@dp.message(Text('Зв\'язатися з підтримкою'))
async def contact_support(message: Message, state: FSMContext):
    await message.answer("Опишіть свою проблему, ми відповімо як можна швидше.")
    await state.set_state(SupportStates.waiting_for_issue_description)

@dp.message(SupportStates.waiting_for_issue_description)
async def receive_issue(message: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"Повідомлення від @{message.from_user.username}: {message.text}")
    await message.answer("Дякуємо! Ваше повідомлення відправлено в підтримку.")
    await state.clear()

@dp.message(Text('Інформація про бренд'))
async def brand_info(message: Message):
    await message.answer(
        "Ми - український бренд одягу, що поєднує військову естетику та сучасний стиль.\n"
        "Слідкуйте за нами в Instagram: https://www.instagram.com/twocomms/"
    )

# Обработка раздела "Запропонувати принт"
@dp.message(Text('🖼️ Запропонувати принт'))
async def propose_print(message: Message):
    await message.answer(
        "Відправте зображення, яке ви хотіли б бачити в якості принта.",
        reply_markup=kb.propose_print_buttons()
    )

@dp.message(Text('Стати дизайнером'))
async def become_designer(message: Message):
    await message.answer("Зв'яжіться з нами для співпраці: @zainllw0w")

@dp.message(content_types=ContentType.PHOTO)
async def receive_proposed_print(message: Message):
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"Пропозиція принта від @{message.from_user.username}")
    await message.answer("Дякуємо! Ми розглянемо ваше зображення.")

# Функция обновления параметров заказа
async def update_parameters(data):
    if data.get('product') == 't_shirt':
        text = (
            f"Ваш вибір:\n"
            f"Розмір футболки: {data.get('size', 'не обрано')}\n"
            f"Задній принт: {'включено' if data.get('back_print') else 'вимкнено'}\n"
            f"Задня надпис: {'включено' if data.get('back_text') else 'вимкнено'}\n"
            f"Made in Ukraine: {'включено' if data.get('made_in_ukraine') else 'вимкнено'}"
        )
    elif data.get('product') == 'hoodie':
        text = (
            f"Ваш вибір:\n"
            f"Розмір худі: {data.get('size', 'не обрано')}\n"
            f"Горловина: {'є' if data.get('collar') else 'немає'}\n"
            f"Задній принт: {'включено' if data.get('back_print') else 'вимкнено'}"
        )
    else:
        text = "Ви ще не обрали товар."
    return text

# Функция расчёта цены
def calculate_price(data):
    base_price = 1150 if data.get('product') == 't_shirt' else 1500
    discount = 0.0
    # Проверяем, одобрены ли скидки
    if data.get('ubd_approved'):
        discount += 0.10
    if data.get('repost_approved'):
        discount += 0.10
    final_price = base_price * (1 - discount)
    return int(final_price)

# Запуск бота
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    dp.run_polling(bot)
