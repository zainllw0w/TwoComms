from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='⚙️ Конструктор замовлення ⚙️')],
            [KeyboardButton(text='📦 Мої замовлення'),
             KeyboardButton(text='🔥 Мої акції та знижки')],
            [KeyboardButton(text='💬 Інформація та підтримка'),
             KeyboardButton(text='🖼️ Запропонувати принт')],
            [KeyboardButton(text='🤝 Співробітництво')]
        ],
        resize_keyboard=True
    )
    return keyboard

def admin_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='⚙️ Конструктор замовлення ⚙️')],
            [KeyboardButton(text='📋 Замовлення')],
            [KeyboardButton(text='📦 Мої замовлення'),
             KeyboardButton(text='🔥 Мої акції та знижки')],
            [KeyboardButton(text='💬 Інформація та підтримка'),
             KeyboardButton(text='🖼️ Запропонувати принт')],
            [KeyboardButton(text='🤝 Співробітництво')]
        ],
        resize_keyboard=True
    )
    return keyboard

def support_response_options():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Питання вирішено', callback_data='support_resolved'),
            InlineKeyboardButton(text='🔄 Задати ще питання', callback_data='support_more_question')
        ]
    ])
    return keyboard

def category_selection_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='👕 Футболки'),
             KeyboardButton(text='🥷🏼 Худі (наразі не має в наявності)')],
            [KeyboardButton(text='🔙 На головну')]
        ],
        resize_keyboard=True
    )
    return keyboard

def size_selection_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='S', callback_data='size_S'),
            InlineKeyboardButton(text='M', callback_data='size_M'),
            InlineKeyboardButton(text='L', callback_data='size_L')
        ],
        [
            InlineKeyboardButton(text='XL', callback_data='size_XL'),
            InlineKeyboardButton(text='XXL', callback_data='size_XXL')
        ],
        [
            InlineKeyboardButton(text='📏 Розмірна сітка', callback_data='size_chart')
        ]
    ])
    return keyboard

def back_to_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='🔙 На головну')]],
        resize_keyboard=True
    )
    return keyboard

def no_orders_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🛠️ Оформити замовлення в конструкторі')],
            [KeyboardButton(text='🔙 На головну')]
        ],
        resize_keyboard=True
    )
    return keyboard

def info_support_buttons():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📞 Зв\'язатися з підтримкою')],
            [KeyboardButton(text='ℹ️ Інформація про бренд')],
            [KeyboardButton(text='🔙 На головну')]
        ],
        resize_keyboard=True
    )
    return keyboard

def payment_options():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='💰 Плата на пошті', callback_data='payment_post'),
            InlineKeyboardButton(text='💳 Оплата на карту', callback_data='payment_card')
        ],
        [
            InlineKeyboardButton(text='❓ Як відбувається доставка?', callback_data='how_delivery')
        ]
    ])
    return keyboard

def paid_button():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Оплачено', callback_data='paid_confirmed')]
    ])
    return keyboard

def approval_buttons(discount_type, user_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Схвалити', callback_data=f'approve_{discount_type}_{user_id}'),
            InlineKeyboardButton(text='❌ Відхилити', callback_data=f'reject_{discount_type}_{user_id}')
        ]
    ])
    return keyboard

def payment_approval_buttons(user_id, order_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Підтвердити оплату', callback_data=f'approve_payment_{user_id}_{order_id}'),
            InlineKeyboardButton(text='❌ Відхилити оплату', callback_data=f'reject_payment_{user_id}_{order_id}')
        ]
    ])
    return keyboard

def admin_order_actions(order_id, statuses):
    buttons = []
    ready_text = '🛠️ Готово до відправки ✅' if statuses.get('ready', False) else '🛠️ Готово до відправки'
    buttons.append([InlineKeyboardButton(text=ready_text, callback_data=f'order_ready_{order_id}')])
    sent_text = '📦 Відправлено ✅' if statuses.get('sent', False) else '📦 Відправлено'
    buttons.append([InlineKeyboardButton(text=sent_text, callback_data=f'order_sent_{order_id}')])
    delivered_text = '✅ Доставлено ✅' if statuses.get('delivered', False) else '✅ Доставлено'
    buttons.append([InlineKeyboardButton(text=delivered_text, callback_data=f'order_delivered_{order_id}')])
    buttons.append([InlineKeyboardButton(text='❌ Відхилити замовлення', callback_data=f'order_cancel_{order_id}')])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

    # Sent
    if statuses.get('sent', False):
        sent_text = '📦 Відправлено ✅'
    else:
        sent_text = '📦 Відправлено'
    buttons.append([
        InlineKeyboardButton(text=sent_text,
                             callback_data=f'order_sent_{order_id}')
    ])
    # Delivered
    if statuses.get('delivered', False):
        delivered_text = '✅ Доставлено ✅'
    else:
        delivered_text = '✅ Доставлено'
    buttons.append([
        InlineKeyboardButton(text=delivered_text,
                             callback_data=f'order_delivered_{order_id}')
    ])
    # Reject order
    buttons.append([
        InlineKeyboardButton(text='❌ Відхилити замовлення',
                             callback_data=f'order_cancel_{order_id}')
    ])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def admin_orders_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📂 Замовлення в обробці')],
            [KeyboardButton(text='📂 Виконані замовлення')],
            [KeyboardButton(text='🔙 На головну')]
        ],
        resize_keyboard=True
    )
    return keyboard


def order_details_button(order_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📄 Деталі замовлення',
                              callback_data=f'order_details_{order_id}')]
    ])
    return keyboard


def admin_support_reply_button(issue_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✉️ Відповісти',
                              callback_data=f'support_reply_{issue_id}')]
    ])
    return keyboard


def product_navigation_keyboard(current_index, total_products,
                                current_color_index, total_colors):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # Кнопки навигации по моделям
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text='⬅️ Назад',
                             callback_data='prev_product'),
        InlineKeyboardButton(text=f"Модель {current_index + 1} з {total_products}",
                             callback_data='noop'),
        InlineKeyboardButton(text='Вперед ➡️',
                             callback_data='next_product')
    ])

    # Кнопки навигации по цветам, если есть несколько цветов
    if total_colors > 1:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text='⬅️ Колір',
                                 callback_data='prev_color'),
            InlineKeyboardButton(text=f"Колір {current_color_index + 1} з {total_colors}",
                                 callback_data='noop'),
            InlineKeyboardButton(text='Колір ➡️',
                                 callback_data='next_color')
        ])

    # Кнопка выбора!
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text='✅ Вибрати',
                             callback_data='select_product')
    ])

    return keyboard


def support_options():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Питання вирішено',
                                 callback_data='support_resolved'),
            InlineKeyboardButton(text='🔄 Задати ще питання',
                                 callback_data='support_more_question')
        ]
    ])
    return keyboard


def options_selection_keyboard(category, selected_options):
    """
    Генерирует клавиатуру для выбора опций в зависимости от категории.
    :param category: 't_shirts' или 'hoodies'
    :param selected_options: dict с текущими выбранными опциями
    :return: InlineKeyboardMarkup
    """
    options = []

    if category == 't_shirts':
        options = [
            ('made_in_ukraine', 'made in Ukraine принт'),
            ('back_text', 'Задня підпис'),
            ('back_print', 'Задній принт')
        ]
    elif category == 'hoodies':
        options = [
            ('collar', 'Горловина'),
            ('sleeve_text', 'Надписи на рукавах'),
            ('back_print', 'Задній принт')
        ]

    buttons = []

    for option_key, option_text in options:
        if selected_options.get(option_key, False):
            text = f"✅ {option_text}"
        else:
            text = f"❌ {option_text}"
        callback_data = f'option_{option_key}'
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    # Добавляем кнопку "➡️ Далі"
    buttons.append([InlineKeyboardButton(text='➡️ Далі', callback_data='options_next')])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard
