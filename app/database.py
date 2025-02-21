# app/database.py

import aiosqlite
import os

DATABASE_PATH = 'app/database.db'


async def init_db():
    """
    Инициализация базы данных. Создание необходимых таблиц.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product TEXT NOT NULL,
                size TEXT,
                back_print BOOLEAN DEFAULT FALSE,
                back_text BOOLEAN DEFAULT FALSE,
                made_in_ukraine BOOLEAN DEFAULT FALSE,
                collar BOOLEAN DEFAULT FALSE,
                sleeve_text BOOLEAN DEFAULT FALSE,
                city TEXT,
                branch TEXT,
                name TEXT,
                phone TEXT,
                payment_method TEXT,
                status TEXT DEFAULT 'Нове',
                price INTEGER,
                ttn TEXT,
                receipt_photo_id TEXT,
                rejection_reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                selected_color_index INTEGER DEFAULT 0,
                admin_message_id INTEGER  -- Новое поле для хранения message_id администратора
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS discounts (
                user_id INTEGER PRIMARY KEY,
                ubd BOOLEAN DEFAULT FALSE,
                repost BOOLEAN DEFAULT FALSE,
                one_time_discount_used BOOLEAN DEFAULT FALSE,
                rejection_reason_ubd TEXT,
                rejection_reason_repost TEXT,
                admin_message_id_ubd INTEGER,
                admin_message_id_repost INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                issue_text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


# Остальной код остается без изменений

# Ниже приведены все функции, которые уже были реализованы в вашем коде

async def get_user_discounts(user_id):
    """
    Получение скидок пользователя.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT ubd, repost FROM discounts WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'ubd': bool(row[0]),
                'repost': bool(row[1])
            }
        else:
            # Если пользователь не имеет скидок, создаём запись
            await db.execute("INSERT INTO discounts (user_id) VALUES (?)", (user_id,))
            await db.commit()
            return {
                'ubd': False,
                'repost': False
            }


async def add_discount(user_id, discount_type):
    """
    Добавление скидки пользователю.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if discount_type == 'ubd':
            await db.execute("UPDATE discounts SET ubd = ? WHERE user_id = ?", (True, user_id))
        elif discount_type == 'repost':
            # При добавлении репост скидки, отмечаем, что одноразовая скидка использована
            await db.execute("UPDATE discounts SET repost = ?, one_time_discount_used = ? WHERE user_id = ?", (True, True, user_id))
        await db.commit()


async def remove_discount(user_id, discount_type):
    """
    Удаление скидки у пользователя.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if discount_type == 'ubd':
            await db.execute("UPDATE discounts SET ubd = ? WHERE user_id = ?", (False, user_id))
        elif discount_type == 'repost':
            await db.execute("UPDATE discounts SET repost = ? WHERE user_id = ?", (False, user_id))
        await db.commit()


async def save_discount_rejection_reason(user_id, discount_type, reason):
    """
    Сохранение причины отказа для скидки.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if discount_type == 'ubd':
            await db.execute("UPDATE discounts SET rejection_reason_ubd = ? WHERE user_id = ?", (reason, user_id))
        elif discount_type == 'repost':
            await db.execute("UPDATE discounts SET rejection_reason_repost = ? WHERE user_id = ?", (reason, user_id))
        await db.commit()


async def is_one_time_discount_used(user_id):
    """
    Проверка, использована ли одноразовая скидка за репост.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT one_time_discount_used FROM discounts WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return bool(row[0])
        return False


async def mark_one_time_discount_used(user_id):
    """
    Отмечает, что одноразовая скидка за репост была использована.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE discounts SET one_time_discount_used = ? WHERE user_id = ?", (True, user_id))
        await db.commit()


async def save_order(user_id, data):
    """
    Сохранение нового заказа в базу данных.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO orders (
                user_id, product, size, back_print, back_text, made_in_ukraine, collar, sleeve_text,
                city, branch, name, phone, payment_method, status, price, selected_color_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get('product'),
            data.get('size'),
            data.get('back_print', False),
            data.get('back_text', False),
            data.get('made_in_ukraine', False),
            data.get('collar', False),
            data.get('sleeve_text', False),
            data.get('city'),
            data.get('branch'),
            data.get('name'),
            data.get('phone'),
            data.get('payment_method'),
            data.get('status', 'Нове'),
            data.get('price'),  # Сохраняем цену
            data.get('selected_color_index', 0)  # Сохраняем выбранный цвет
        ))
        await db.commit()
        cursor = await db.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        return row[0]  # Возвращаем ID заказа


async def get_orders_by_user(user_id):
    """
    Получение всех заказов пользователя.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        orders = []
        for row in rows:
            orders.append({
                'id': row[0],
                'user_id': row[1],
                'product': row[2],
                'size': row[3],
                'back_print': bool(row[4]),
                'back_text': bool(row[5]),
                'made_in_ukraine': bool(row[6]),
                'collar': bool(row[7]),
                'sleeve_text': bool(row[8]),
                'city': row[9],
                'branch': row[10],
                'name': row[11],
                'phone': row[12],
                'payment_method': row[13],
                'status': row[14],
                'price': row[15],
                'ttn': row[16],  # Новое поле
                'receipt_photo_id': row[17],  # Новое поле
                'rejection_reason': row[18],  # Новое поле
                'timestamp': row[19],
                'selected_color_index': row[20],  # Новое поле
                'admin_message_id': row[21]  # Новое поле
            })
        return orders


async def get_order_by_id(order_id):
    """
    Получение заказа по ID.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'product': row[2],
                'size': row[3],
                'back_print': bool(row[4]),
                'back_text': bool(row[5]),
                'made_in_ukraine': bool(row[6]),
                'collar': bool(row[7]),
                'sleeve_text': bool(row[8]),
                'city': row[9],
                'branch': row[10],
                'name': row[11],
                'phone': row[12],
                'payment_method': row[13],
                'status': row[14],
                'price': row[15],
                'ttn': row[16],
                'receipt_photo_id': row[17],
                'rejection_reason': row[18],
                'timestamp': row[19],
                'selected_color_index': row[20],
                'admin_message_id': row[21]
            }
        return None


async def get_orders_not_delivered():
    """
    Получение всех заказов, которые еще не доставлены.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE status != 'Доставлено' AND status != 'Відхилено'")
        rows = await cursor.fetchall()
        orders = []
        for row in rows:
            orders.append({
                'id': row[0],
                'user_id': row[1],
                'product': row[2],
                'size': row[3],
                'back_print': bool(row[4]),
                'back_text': bool(row[5]),
                'made_in_ukraine': bool(row[6]),
                'collar': bool(row[7]),
                'sleeve_text': bool(row[8]),
                'city': row[9],
                'branch': row[10],
                'name': row[11],
                'phone': row[12],
                'payment_method': row[13],
                'status': row[14],
                'price': row[15],
                'ttn': row[16],
                'receipt_photo_id': row[17],
                'rejection_reason': row[18],
                'timestamp': row[19],
                'selected_color_index': row[20],
                'admin_message_id': row[21]
            })
        return orders


async def get_orders_by_status(status):
    """
    Получение всех заказов по статусу.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE status = ?", (status,))
        rows = await cursor.fetchall()
        orders = []
        for row in rows:
            orders.append({
                'id': row[0],
                'user_id': row[1],
                'product': row[2],
                'size': row[3],
                'back_print': bool(row[4]),
                'back_text': bool(row[5]),
                'made_in_ukraine': bool(row[6]),
                'collar': bool(row[7]),
                'sleeve_text': bool(row[8]),
                'city': row[9],
                'branch': row[10],
                'name': row[11],
                'phone': row[12],
                'payment_method': row[13],
                'status': row[14],
                'price': row[15],
                'ttn': row[16],
                'receipt_photo_id': row[17],
                'rejection_reason': row[18],
                'timestamp': row[19],
                'selected_color_index': row[20],
                'admin_message_id': row[21]
            })
        return orders


async def update_order_status(order_id, new_status):
    """
    Обновление статуса заказа.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        await db.commit()


async def update_order_ttn(order_id, ttn):
    """
    Обновление номера ТТН заказа.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE orders SET ttn = ? WHERE id = ?", (ttn, order_id))
        await db.commit()


async def save_order_receipt(order_id, receipt_photo_id):
    """
    Сохранение скриншота квитанции оплаты.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE orders SET receipt_photo_id = ? WHERE id = ?", (receipt_photo_id, order_id))
        await db.commit()


async def save_order_rejection_reason(order_id, reason):
    """
    Сохранение причины отказа для заказа.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE orders SET rejection_reason = ? WHERE id = ?", (reason, order_id))
        await db.commit()


async def save_user_issue(user_id, issue_text):
    """
    Сохранение обращения пользователя в поддержку.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO support_issues (user_id, issue_text) VALUES (?, ?)
        """, (user_id, issue_text))
        await db.commit()
        cursor = await db.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        return row[0]  # Возвращаем ID обращения


async def get_user_issue(issue_id):
    """
    Получение обращения пользователя по ID.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT * FROM support_issues WHERE id = ?", (issue_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'issue_text': row[2],
                'timestamp': row[3]
            }
        return None


async def save_order_admin_message_id(order_id, message_id):
    """
    Сохранение message_id сообщения администратора для заказа.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE orders SET admin_message_id = ? WHERE id = ?", (message_id, order_id))
        await db.commit()


async def save_discount_admin_message_id(user_id, discount_type, message_id):
    """
    Сохранение message_id сообщения администратора для скидки.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if discount_type == 'ubd':
            await db.execute("UPDATE discounts SET admin_message_id_ubd = ? WHERE user_id = ?", (message_id, user_id))
        elif discount_type == 'repost':
            await db.execute("UPDATE discounts SET admin_message_id_repost = ? WHERE user_id = ?", (message_id, user_id))
        await db.commit()
