import logging
import sqlite3
import random
import os
import asyncio
import json
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден!")

request = HTTPXRequest()

# ========== КОНФИГУРАЦИЯ КЕЙСОВ ==========

BASE_CASE_ITEMS = [
    {"name": "Максим Абакумов", "chance": 50},
    {"name": "Кирилл Чемакин", "chance": 25},
    {"name": "Максим Едапин", "chance": 13},
    {"name": "Дамир Таликин", "chance": 7},
    {"name": "Михаил Петров", "chance": 5},
]

ATTACK_CASE_ITEMS = [
    {"name": "Максим Абакумов", "chance": 50},
    {"name": "Артем Аношин", "chance": 30},
    {"name": "Максим Дмитриев", "chance": 15},
    {"name": "Руслан Болов", "chance": 5},
]

CASE_ITEMS = {"base": BASE_CASE_ITEMS, "attack": ATTACK_CASE_ITEMS}
CASE_PRICES = {"base": 1.0, "attack": 1.5}
CASE_NAMES = {"base": "📦 Базовый кейс", "attack": "⚔️ Нападающий кейс"}

# ========== ВОПРОСЫ ВИКТОРИНЫ ==========
EASY_QUESTIONS = [
    {"question": "В каком году основан ФК «Тюмень»?", "options": ["1960", "1961", "1970"], "correct": "1961"},
    {"question": "Как называется нынешний стадион «Тюмени»?", "options": ["Геолог", "Строймаш", "Центральный"], "correct": "Геолог"},
    {"question": "Как зовут директора ФК «Тюмень»?", "options": ["Тимур Касимов", "Андрей Семенов", "Александр Попов"], "correct": "Александр Попов"},
]

MEDIUM_QUESTIONS = [
    {"question": "Кто играет под 89 номером?", "options": ["Андрей Дернов", "Артем Лутцев", "Кирилл Чемакин"], "correct": "Артем Лутцев"},
    {"question": "Из какого клуба был арендован Дмитрий Бегун?", "options": ["Балтика Калининград", "Сокол Саратов", "СКА-Хабаровск"], "correct": "Балтика Калининград"},
    {"question": "Кто был главным тренером до Тимура Касимова?", "options": ["Игорь Меньщиков", "Горан Алексич", "Сергей Попков"], "correct": "Сергей Попков"},
]

# ========== ЛОКАЛЬНЫЕ ФОТО ==========
def get_player_image_path(player_name):
    images = {
        "Максим Абакумов": "images/abakumov.png",
        "Кирилл Чемакин": "images/chemakin.png",
        "Максим Едапин": "images/edapin.jpg",
        "Дамир Таликин": "images/talikin.png",
        "Михаил Петров": "images/petrov.png",
        "Артем Аношин": "images/anoshin.png",
        "Максим Дмитриев": "images/dmitriev.jpg",
        "Руслан Болов": "images/bolov.png",
    }
    return images.get(player_name)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========

def init_database():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            total_answers INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            level1_completed INTEGER DEFAULT 0,
            level2_completed INTEGER DEFAULT 0,
            inventory TEXT DEFAULT '{}'
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def get_balance(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0.0

def update_balance(user_id, new_balance):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone()
    if not exists:
        cursor.execute('INSERT INTO users (user_id, username, first_name, balance, total_answers, correct_answers, level1_completed, level2_completed, inventory) VALUES (?, ?, ?, 0, 0, 0, 0, 0, ?)', 
                      (user_id, username, first_name, json.dumps({})))
        conn.commit()
        print(f"✅ Новый пользователь добавлен: {user_id}")
    else:
        cursor.execute('UPDATE users SET username = ?, first_name = ? WHERE user_id = ?', 
                      (username, first_name, user_id))
        conn.commit()
    conn.close()

def update_quiz_stats(user_id, is_correct):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET total_answers = total_answers + 1 WHERE user_id = ?', (user_id,))
    if is_correct:
        cursor.execute('UPDATE users SET correct_answers = correct_answers + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_quiz_stats(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT total_answers, correct_answers FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0)

def get_level_completed(user_id, level):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    if level == 1:
        cursor.execute('SELECT level1_completed FROM users WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('SELECT level2_completed FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def set_level_completed(user_id, level):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    if level == 1:
        cursor.execute('UPDATE users SET level1_completed = 1 WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('UPDATE users SET level2_completed = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    print(f"✅ Уровень {level} отмечен как пройденный для {user_id}")

def get_inventory(user_id):
    """Получает инвентарь пользователя в виде словаря"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT inventory FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return json.loads(result[0])
    return {}

def update_inventory(user_id, item_name):
    """Добавляет предмет в инвентарь"""
    inventory = get_inventory(user_id)
    
    if item_name in inventory:
        inventory[item_name] += 1
    else:
        inventory[item_name] = 1
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET inventory = ? WHERE user_id = ?', (json.dumps(inventory), user_id))
    conn.commit()
    conn.close()
    print(f"✅ Добавлен {item_name} в инвентарь {user_id}")

def get_random_item(case_type):
    items = CASE_ITEMS[case_type]
    chances = [item["chance"] for item in items]
    selected = random.choices(items, weights=chances, k=1)[0]
    return selected["name"]

# ========== КЛАВИАТУРА ==========
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("❓ Викторина")],
        [KeyboardButton("💼 Кейсы")],
        [KeyboardButton("👆 Кликер")],
        [KeyboardButton("👤 Профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or "", user.first_name or "")
    await update.message.reply_text(
        "🖐️Привет! Это бот создан про наш тюменский клуб. Здесь будет много разного контента, обещаем проект будет развиваться!",
        reply_markup=get_main_keyboard()
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username if user.username else "не указан"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "не указано"
    balance = get_balance(user.id)
    total, correct = get_quiz_stats(user.id)
    
    if total > 0:
        percent = (correct / total) * 100
        quiz_stats = f"{correct}/{total} ({percent:.1f}%)"
    else:
        quiz_stats = "0/0 (0%)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧰 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton("‼️ Предложения", callback_data="suggestions")]
    ])
    
    await update.message.reply_text(
        f"📋 Ваш профиль\n\n"
        f"👤 Имя: {full_name}\n"
        f"🔹 Username: @{username}\n"
        f"💰 Баланс: {balance:.2f} coins\n"
        f"📊 Викторина: {quiz_stats} правильных ответов",
        reply_markup=keyboard
    )

async def clicker_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔘 КЛИКАЙ (+0.02)", callback_data="click")]])
    await update.message.reply_text(
        f"🎮 *Кликер*\n\n💰 *Баланс:* {balance:.2f} coins\n\n👇 Нажимай кнопку ниже!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def handle_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current_balance = get_balance(user_id)
    new_balance = current_balance + 0.02
    update_balance(user_id, new_balance)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔘 КЛИКАЙ (+0.02)", callback_data="click")]])
    try:
        await query.message.edit_text(
            f"🎮 *Кликер*\n\n💰 *Баланс:* {new_balance:.2f} coins\n\n👇 Нажимай кнопку ниже!",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ========== ИНВЕНТАРЬ ==========
async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает инвентарь пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    inventory = get_inventory(user_id)
    
    if not inventory:
        await query.message.reply_text(
            "🧰 *Ваш инвентарь пуст*\n\n"
            "Открывайте кейсы, чтобы получить футболистов!",
            parse_mode="Markdown"
        )
        return
    
    # Формируем список предметов
    items_list = ""
    for item_name, count in sorted(inventory.items()):
        items_list += f"• {item_name}: {count} шт\n"
    
    # Подсчитываем общее количество
    total_items = sum(inventory.values())
    
    await query.message.reply_text(
        f"🧰 *Ваш инвентарь*\n\n"
        f"📦 Всего предметов: {total_items}\n\n"
        f"{items_list}",
        parse_mode="Markdown"
    )

# ========== ПРЕДЛОЖЕНИЯ ==========
async def suggestions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает меню предложений"""
    query = update.callback_query
    user_id = query.from_user.id
    print(f"🔍 Пользователь {user_id} нажал кнопку Предложения")
    
    await query.answer()
    
    context.user_data['waiting_for_suggestion'] = True
    print(f"✅ Для пользователя {user_id} установлен режим ожидания предложения")
    
    await query.message.reply_text(
        "📝 Предложения и вопросы\n\n"
        "Здесь вы можете предложить идеи по боту, а также написать вопрос, "
        "который я смогу задать лично тренеру «Тюмени» или другой команды "
        "(вопросы проходят модерацию).\n\n"
        "✍️ Напиши своё предложение или вопрос одним сообщением:"
    )

async def handle_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает отправленное предложение"""
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else "нет username"
    first_name = user.first_name if user.first_name else ""
    text = update.message.text
    
    if not context.user_data.get('waiting_for_suggestion'):
        return False
    
    context.user_data['waiting_for_suggestion'] = False
    
    ADMIN_ID = 2120093748
    
    admin_text = f"📬 НОВОЕ ПРЕДЛОЖЕНИЕ!\n\nОт: {first_name} (@{username})\nID: {user_id}\n\nТекст:\n{text}"
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text
        )
        await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )
    except Exception as e:
        print(f"❌ Ошибка при отправке админу: {e}")
    
    await update.message.reply_text(
        "✅ Спасибо что написал!\n\nЖди когда администратор прочитает это сообщение."
    )
    
    return True

# ========== КЕЙСЫ ==========
async def cases_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Базовый кейс (1 coin)", callback_data="show_base")],
        [InlineKeyboardButton("⚔️ Нападающий кейс (1.5 coin)", callback_data="show_attack")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_menu")]
    ])
    await update.message.reply_text(
        f"📦 *Магазин кейсов*\n\n💰 *Твой баланс:* {balance:.2f} coins\n\nВыбери кейс:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def show_case_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    case_type = query.data.replace("show_", "")
    if case_type == "base":
        name = "📦 Базовый кейс"
        price = 1.0
        items = BASE_CASE_ITEMS
    else:
        name = "⚔️ Нападающий кейс"
        price = 1.5
        items = ATTACK_CASE_ITEMS
    
    items_list = ""
    for item in items:
        items_list += f"• {item['name']} — {item['chance']}%\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 ОТКРЫТЬ", callback_data=f"open_{case_type}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_cases")]
    ])
    await query.message.edit_text(
        f"{name}\n\n💰 *Цена:* {price} coin\n\n📋 *Содержимое:*\n{items_list}\n⬇️ Нажми «Открыть»!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def handle_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    case_type = query.data.replace("open_", "")
    price = CASE_PRICES.get(case_type, 0)
    name = CASE_NAMES.get(case_type, "Кейс")
    balance = get_balance(user_id)
    
    if balance < price:
        await query.message.edit_text(
            f"❌ *Недостаточно монет!*\n\n📦 {name} стоит {price} coins\n💰 Твой баланс: {balance:.2f} coins",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_cases")]])
        )
        return
    
    new_balance = balance - price
    update_balance(user_id, new_balance)
    item_name = get_random_item(case_type)
    
    # Добавляем в инвентарь
    update_inventory(user_id, item_name)
    
    image_path = get_player_image_path(item_name)
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, 'rb') as photo:
                await query.message.reply_photo(
                    photo=InputFile(photo),
                    caption=f"🎁 *{name}*\n\n✨ Тебе выпал:\n**{item_name}**\n\n💰 Осталось: {new_balance:.2f} coins",
                    parse_mode="Markdown"
                )
            await query.message.delete()
            return
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Открыть ещё", callback_data=f"open_{case_type}")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_cases")]
    ])
    await query.message.edit_text(
        f"🎁 *{name}*\n\n✨ Тебе выпал:\n**{item_name}**\n\n💰 Осталось: {new_balance:.2f} coins",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ========== ВИКТОРИНА ==========
async def quiz_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    level1_completed = get_level_completed(user_id, 1)
    level2_completed = get_level_completed(user_id, 2)
    
    buttons = []
    
    if level1_completed == 1:
        buttons.append([InlineKeyboardButton("1️⃣ Уровень 1 ✅ (пройден)", callback_data="quiz_already_completed")])
    else:
        buttons.append([InlineKeyboardButton("1️⃣ Уровень 1", callback_data="quiz_easy")])
    
    if level2_completed == 1:
        buttons.append([InlineKeyboardButton("2️⃣ Уровень 2 ✅ (пройден)", callback_data="quiz_already_completed")])
    else:
        buttons.append([InlineKeyboardButton("2️⃣ Уровень 2", callback_data="quiz_medium")])
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        "❓ *Викторина*\n\n"
        "👇 *Выбери уровень.*\n"
        "Пройдешь викторину — получишь +0.1 coin!\n\n"
        "⚠️ *Каждый уровень можно пройти только один раз!*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    difficulty = query.data.replace("quiz_", "")
    
    if difficulty == "easy":
        if get_level_completed(user_id, 1) == 1:
            await query.message.edit_text("❌ *Ты уже прошел Уровень 1!*", parse_mode="Markdown")
            return
        questions = EASY_QUESTIONS.copy()
        random.shuffle(questions)
        context.user_data['quiz_questions'] = questions
        context.user_data['quiz_index'] = 0
        context.user_data['quiz_difficulty'] = "easy"
        context.user_data['quiz_level'] = 1
        await ask_question(query, context)
    elif difficulty == "medium":
        if get_level_completed(user_id, 2) == 1:
            await query.message.edit_text("❌ *Ты уже прошел Уровень 2!*", parse_mode="Markdown")
            return
        questions = MEDIUM_QUESTIONS.copy()
        random.shuffle(questions)
        context.user_data['quiz_questions'] = questions
        context.user_data['quiz_index'] = 0
        context.user_data['quiz_difficulty'] = "medium"
        context.user_data['quiz_level'] = 2
        await ask_question(query, context)

async def ask_question(query, context):
    questions = context.user_data.get('quiz_questions', [])
    index = context.user_data.get('quiz_index', 0)
    user_id = query.from_user.id
    level = context.user_data.get('quiz_level', 1)
    
    if get_level_completed(user_id, level) == 1:
        await query.message.edit_text("❌ *Ты уже прошел этот уровень!*", parse_mode="Markdown")
        return
    
    if index >= len(questions):
        set_level_completed(user_id, level)
        current_balance = get_balance(user_id)
        new_balance = current_balance + 0.1
        update_balance(user_id, new_balance)
        
        difficulty_name = "Уровень 1" if level == 1 else "Уровень 2"
        
        await query.message.edit_text(
            f"🎉 *Поздравляю!*\n\n"
            f"Ты прошел {difficulty_name}!\n"
            f"💰 +0.1 coin\n"
            f"💰 Новый баланс: {new_balance:.2f} coins",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_menu")]])
        )
        return
    
    q = questions[index]
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"quiz_answer_{opt}")] for opt in q['options']]
    await query.message.edit_text(
        f"❓ *Вопрос {index + 1}/{len(questions)}*\n\n{q['question']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    answer = query.data.replace("quiz_answer_", "")
    questions = context.user_data.get('quiz_questions', [])
    index = context.user_data.get('quiz_index', 0)
    user_id = query.from_user.id
    level = context.user_data.get('quiz_level', 1)
    
    if get_level_completed(user_id, level) == 1:
        await query.message.edit_text("❌ *Ты уже прошел этот уровень!*", parse_mode="Markdown")
        return
    
    if index >= len(questions):
        return
    
    current_q = questions[index]
    
    if answer == current_q['correct']:
        update_quiz_stats(user_id, True)
        await query.message.edit_text("✅ *Верно, красавчик!*", parse_mode="Markdown")
        context.user_data['quiz_index'] = index + 1
        await asyncio.sleep(1.5)
        await ask_question(query, context)
    else:
        update_quiz_stats(user_id, False)
        await query.message.edit_text("❌ *Неверно!*\n\n🔄 Начинаем викторину заново!", parse_mode="Markdown")
        await asyncio.sleep(2)
        
        difficulty = context.user_data.get('quiz_difficulty', 'easy')
        if difficulty == 'easy':
            new_questions = EASY_QUESTIONS.copy()
        else:
            new_questions = MEDIUM_QUESTIONS.copy()
        
        random.shuffle(new_questions)
        context.user_data['quiz_questions'] = new_questions
        context.user_data['quiz_index'] = 0
        
        await ask_question(query, context)

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def handle_quiz_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔧 В разработке! Скоро появится!", show_alert=True)

async def handle_quiz_already_completed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Ты уже прошел этот уровень!", show_alert=True)

# ========== НАВИГАЦИЯ ==========
async def handle_back_to_cases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = get_balance(user_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Базовый кейс (1 coin)", callback_data="show_base")],
        [InlineKeyboardButton("⚔️ Нападающий кейс (1.5 coin)", callback_data="show_attack")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_menu")]
    ])
    await query.message.edit_text(
        f"📦 *Магазин кейсов*\n\n💰 *Твой баланс:* {balance:.2f} coins\n\nВыбери кейс:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def handle_back_to_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    level1_completed = get_level_completed(user_id, 1)
    level2_completed = get_level_completed(user_id, 2)
    
    buttons = []
    
    if level1_completed == 1:
        buttons.append([InlineKeyboardButton("1️⃣ Уровень 1 ✅ (пройден)", callback_data="quiz_already_completed")])
    else:
        buttons.append([InlineKeyboardButton("1️⃣ Уровень 1", callback_data="quiz_easy")])
    
    if level2_completed == 1:
        buttons.append([InlineKeyboardButton("2️⃣ Уровень 2 ✅ (пройден)", callback_data="quiz_already_completed")])
    else:
        buttons.append([InlineKeyboardButton("2️⃣ Уровень 2", callback_data="quiz_medium")])
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    await query.message.edit_text(
        "❓ *Викторина*\n\n👇 *Выбери уровень.*\nПройдешь — получишь +0.1 coin!\n\n⚠️ *Каждый уровень можно пройти только один раз!*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def handle_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await query.message.chat.send_message(
        "🔙 *Главное меню*",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if context.user_data.get('waiting_for_suggestion'):
        await handle_suggestion(update, context)
        return
    
    add_user(user_id, update.effective_user.username or "", update.effective_user.first_name or "")
    
    if text == "👤 Профиль":
        await profile(update, context)
    elif text == "👆 Кликер":
        await clicker_menu(update, context)
    elif text == "💼 Кейсы":
        await cases_menu(update, context)
    elif text == "❓ Викторина":
        await quiz_menu(update, context)
    else:
        await update.message.reply_text(
            "Используй кнопки внизу 👇",
            reply_markup=get_main_keyboard()
        )

# ========== АДМИН-КОМАНДА ==========
async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ADMIN_ID = 2120093748
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи количество: /addcoins 100")
        return
    
    try:
        amount = float(context.args[0])
    except:
        await update.message.reply_text("❌ Введи число!")
        return
    
    current = get_balance(user_id)
    new_balance = current + amount
    update_balance(user_id, new_balance)
    await update.message.reply_text(f"✅ Добавлено {amount} монет!\n💰 Новый баланс: {new_balance:.2f} coins")

# ========== ЗАПУСК ==========
def main():
    print("🚀 Запуск бота...")
    init_database()
    
    if not os.path.exists("images"):
        os.makedirs("images")
        print("📁 Создана папка images/")
    
    application = Application.builder().token(BOT_TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addcoins", add_coins))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_click, pattern="click"))
    application.add_handler(CallbackQueryHandler(show_inventory, pattern="^inventory$"))
    application.add_handler(CallbackQueryHandler(suggestions_menu, pattern="^suggestions$"))
    application.add_handler(CallbackQueryHandler(start_quiz, pattern="^quiz_(easy|medium)$"))
    application.add_handler(CallbackQueryHandler(handle_quiz_answer, pattern="^quiz_answer_"))
    application.add_handler(CallbackQueryHandler(show_case_info, pattern="^show_"))
    application.add_handler(CallbackQueryHandler(handle_case, pattern="^open_"))
    application.add_handler(CallbackQueryHandler(handle_back_to_cases, pattern="^back_to_cases$"))
    application.add_handler(CallbackQueryHandler(handle_back_to_quiz, pattern="^back_to_quiz$"))
    application.add_handler(CallbackQueryHandler(handle_back_to_menu, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(handle_quiz_coming_soon, pattern="^quiz_coming_soon$"))
    application.add_handler(CallbackQueryHandler(handle_quiz_already_completed, pattern="^quiz_already_completed$"))
    
    print("🤖 Бот запущен! Напиши /start в Telegram")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()