# app/fetch_instagram.py

import requests
import json
import os
from datetime import datetime
import re
import logging

# Загрузка переменных окружения
from dotenv import load_dotenv
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fetch_instagram.log"),  # Логирование в файл
        logging.StreamHandler()  # Логирование в консоль
    ]
)

INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID')
ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')

# Проверка наличия необходимых переменных окружения
if not INSTAGRAM_BUSINESS_ACCOUNT_ID or not ACCESS_TOKEN:
    logging.error("Необходимо установить INSTAGRAM_BUSINESS_ACCOUNT_ID и ACCESS_TOKEN в .env файле.")
    exit(1)

# Определяем путь относительно текущего файла
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_JSON_PATH = os.path.join(BASE_DIR, 'products.json')

# Хештеги для фильтрации
HASHTAG_TS = '#ts'
HASHTAG_HD = '#hd'

def get_recent_media():
    """
    Получает последние медиа из Instagram аккаунта.
    """
    url = f'https://graph.facebook.com/v21.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media'
    params = {
        'fields': 'id,caption,media_type,media_url,permalink,timestamp,children{media_type,media_url}',
        'access_token': ACCESS_TOKEN,
        'limit': 100  # Максимальное количество медиа за один запрос
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        logging.info(f"Получено {len(data.get('data', []))} медиа-постов.")
        return data.get('data', [])
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP ошибка при получении медиа: {http_err}")
    except Exception as err:
        logging.error(f"Ошибка при получении медиа: {err}")
    return []

def load_existing_products():
    """
    Загружает существующие продукты из JSON файла или инициализирует структуру.
    """
    if not os.path.exists(PRODUCTS_JSON_PATH):
        # Инициализируем пустую структуру
        logging.info("Файл products.json не найден. Инициализирую пустую структуру.")
        return {
            "t_shirts": [],
            "hoodies": []
        }
    try:
        with open(PRODUCTS_JSON_PATH, 'r', encoding='utf-8') as f:
            products = json.load(f)
            logging.info(f"Загружено {len(products.get('t_shirts', []))} футболок и {len(products.get('hoodies', []))} худі из products.json.")
            return products
    except json.JSONDecodeError:
        logging.warning("Ошибка декодирования JSON. Инициализирую пустую структуру.")
        return {
            "t_shirts": [],
            "hoodies": []
        }
    except Exception as e:
        logging.error(f"Ошибка при загрузке продуктов: {e}")
        return {
            "t_shirts": [],
            "hoodies": []
        }

def save_products(products):
    """
    Сохраняет обновлённые продукты в JSON файл.
    """
    try:
        with open(PRODUCTS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=4)
        logging.info(f"✅ Продукты успешно сохранены в {PRODUCTS_JSON_PATH}.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении продуктов: {e}")

def extract_hashtags(caption):
    """
    Извлекает хештеги из подписи поста.
    """
    if not caption:
        return []
    hashtags = re.findall(r'#\w+', caption.lower())
    return hashtags

def fetch_and_update_products():
    """
    Основная функция для получения и обновления продуктов.
    """
    logging.info("Начинаю обновление продуктовых данных.")
    media = get_recent_media()
    if not media:
        logging.error("❌ Нет доступных медиа или произошла ошибка при получении данных.")
        return

    products = load_existing_products()
    t_shirts = products.get('t_shirts', [])
    hoodies = products.get('hoodies', [])

    # Собираем существующие model_id для избежания дубликатов
    existing_ts_ids = {item['model_id']: item for item in t_shirts}
    existing_hd_ids = {item['model_id']: item for item in hoodies}

    new_products_count = 0

    for post in media:
        caption = post.get('caption', '').lower()
        hashtags = extract_hashtags(caption)
        logging.info(f"📄 Обрабатывается пост ID: {post.get('id')}, хэштеги: {hashtags}")

        is_ts = HASHTAG_TS in hashtags
        is_hd = HASHTAG_HD in hashtags

        if not (is_ts or is_hd):
            logging.info("❌ Пропускаем пост без нужных хэштегов.")
            continue

        product_type = 't_shirts' if is_ts else 'hoodies'
        logging.info(f"📦 Обнаружена категория: {product_type}")

        # Извлекаем ссылки на изображения
        media_type = post.get('media_type')
        images = []

        if media_type == 'IMAGE':
            images.append(post.get('media_url'))
        elif media_type == 'CAROUSEL_ALBUM':
            children = post.get('children', {}).get('data', [])
            for child in children:
                if child.get('media_type') == 'IMAGE':
                    images.append(child.get('media_url'))
        else:
            logging.warning(f"⚠️ Пропускаем пост с типом медиа: {media_type}")
            continue

        if not images:
            logging.warning(f"⚠️ Пост {post.get('id')} не содержит изображений.")
            continue

        # Генерируем model_id и model_name
        model_id = f"{'ts' if product_type == 't_shirts' else 'hd'}{post.get('id')}"
        model_name = f"{'Футболка' if product_type == 't_shirts' else 'Худі'} Model {post.get('id')[-4:]}"

        # Проверяем, существует ли уже эта модель
        existing_products = existing_ts_ids if product_type == 't_shirts' else existing_hd_ids

        if model_id in existing_products:
            # Обновляем список цветов для существующей модели
            existing_product = existing_products[model_id]
            # Добавляем новые изображения, избегая дубликатов
            existing_images = set(existing_product.get('colors', []))
            new_images = [img for img in images if img not in existing_images]
            if new_images:
                existing_product['colors'].extend(new_images)
                logging.info(f"🔄 Обновлена модель {model_name}: добавлено {len(new_images)} новых цветов.")
            else:
                logging.info(f"🔄 Модель {model_name} уже содержит все изображения. Пропускаем.")
            continue
        else:
            # Добавляем новую модель
            new_model = {
                "model_id": model_id,
                "model_name": model_name,
                "colors": images
            }
            if product_type == 't_shirts':
                t_shirts.append(new_model)
                existing_ts_ids[model_id] = new_model
            else:
                hoodies.append(new_model)
                existing_hd_ids[model_id] = new_model

            new_products_count += 1
            logging.info(f"✅ Добавлена новая {product_type[:-1].capitalize()}: {model_name} с {len(images)} цветами.")

    # Обновляем структуру продуктов
    products['t_shirts'] = t_shirts
    products['hoodies'] = hoodies

    # Сохраняем обратно в JSON файл
    save_products(products)

    logging.info(f"📦 Обновление продуктовых данных завершено. Добавлено {new_products_count} новых продуктов.")

if __name__ == '__main__':
    fetch_and_update_products()
