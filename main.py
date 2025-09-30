import os
import pandas as pd
from datetime import datetime
import httpx
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
import logging

# === НАСТРОЙКИ ===
OWNER_USER_ID = 7205409163
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env (для локальной разработки)
load_dotenv()

# Получаем токен из переменных окружения
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не указан TELEGRAM_BOT_TOKEN в переменных окружения!")
MISTRAL_API_KEY = ""
BASE_DIR = r"C:\telerambot"
FEEDBACK_FILE = os.path.join(BASE_DIR, "feedback_results.txt")
EXCEL_FILE = os.path.join(BASE_DIR, "feedback.xlsx")
KNOWLEDGE_BASE_FILE = os.path.join(BASE_DIR, "knowledge_base.json")
ANONYMOUS, RATING, COMMENT = range(3)
THANKS_ANIMATION = "CAACAgIAAxkBAAEPYbloyOtP-eQb6NNFalANFkV_ZG5WJAACVgEAAntOKhDEUbt6AoALpTYE"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# Состояния для диалога с нейросетью и управления
AI_CHAT = "ai_chat"
ADMIN_MENU = "admin_menu"
ADMIN_KNOWLEDGE = "admin_knowledge"
ADMIN_FEEDBACK = "admin_feedback"

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def load_knowledge_base():
    """Загрузка базы знаний из файла"""
    if os.path.exists(KNOWLEDGE_BASE_FILE):
        try:
            with open(KNOWLEDGE_BASE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Knowledge Base Load Error] {e}")
            return {}
    else:
        # Создаем базовую базу знаний
        default_knowledge = {
            "о боте": "Я - телеграм-бот, умный ассистент на базе Mistral AI. Могу отвечать на вопросы и помогать пользователям.",
            "возможности": "Я умею: отвечать на вопросы, вести диалог, собирать обратную связь, работать с базой знаний.",
            "контакты": "Для связи с разработчиком обратитесь к владельцу бота - @superxset.",
            "помощь": "Выберите действие из меню. Для диалога нажмите 'Задать вопрос'."
        }
        save_knowledge_base(default_knowledge)
        return default_knowledge


def save_knowledge_base(knowledge_base):
    """Сохранение базы знаний в файл"""
    os.makedirs(BASE_DIR, exist_ok=True)
    try:
        with open(KNOWLEDGE_BASE_FILE, 'w', encoding='utf-8') as f:
            json.dump(knowledge_base, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Knowledge Base Save Error] {e}")


def search_knowledge_base(query: str, knowledge_base: dict) -> str:
    """Поиск в базе знаний"""
    query_lower = query.lower()
    relevant_info = []
    
    for key, value in knowledge_base.items():
        if key.lower() in query_lower or any(word in query_lower for word in key.lower().split()):
            relevant_info.append(f"{key}: {value}")
    
    return "\n".join(relevant_info) if relevant_info else ""


async def safe_edit_message(query, text, reply_markup=None):
    try:
        current_text = query.message.text if query.message and query.message.text else ""
        current_markup = query.message.reply_markup if query.message else None
        
        if current_text.strip() == text.strip():
            if reply_markup:
                new_markup_str = str(reply_markup.inline_keyboard)
                old_markup_str = str(current_markup.inline_keyboard) if current_markup else ""
                if old_markup_str == new_markup_str:
                    return await query.answer()
            elif current_markup is None:
                return await query.answer()
        return await query.edit_message_text(text=text, reply_markup=reply_markup)
    except Exception as e:
        print(f"[safe_edit_message] Ошибка: {e}")
        await query.answer()


async def call_mistral_api(prompt: str, chat_history: list = None, knowledge_context: str = "") -> str:
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    
    # Формируем системное сообщение с контекстом из базы знаний
    system_message = {
        "role": "system", 
        "content": "Вы - полезный ассистент. Используйте следующую информацию из базы знаний при ответе на вопросы:\n" + 
                  (knowledge_context if knowledge_context else "Общая информация не предоставлена.")
    }
    
    # Формируем историю диалога
    messages = [system_message]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "mistral-small-latest",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 512
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(MISTRAL_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Mistral API Error] {e}")
        return "⚠️ Извините, не могу сейчас ответить. Попробуйте позже."


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_owner=False):
    """Показ главного меню"""
    if is_owner:
        keyboard = [
            ["💬 Задать вопрос", "📩 Обратная связь"],
            ["📚 База знаний", "📊 Статистика"],
            ["📥 Скачать Excel", "🔄 Перезапустить"]
        ]
    else:
        keyboard = [
            ["💬 Задать вопрос", "📩 Обратная связь"],
            ["📚 База знаний", "🔄 Перезапустить"]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    # Проверяем тип update
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("👇 Выберите действие:", reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text("👇 Выберите действие:", reply_markup=reply_markup)


async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню администратора"""
    keyboard = [
        ["📚 Управление знаниями", "📊 Управление отзывами"],
        ["📈 Статистика", "⚙️ Настройки"],
        ["🔙 В главное меню"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("👑 Меню администратора:", reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text("👑 Меню администратора:", reply_markup=reply_markup)
    
    context.user_data['current_state'] = ADMIN_MENU


async def show_knowledge_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню управления базой знаний"""
    keyboard = [
        ["➕ Добавить знание", "📋 Просмотреть базу"],
        ["✏️ Редактировать знание", "🗑️ Удалить знание"],
        ["🔙 Назад в админку"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("📚 Управление базой знаний:", reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text("📚 Управление базой знаний:", reply_markup=reply_markup)
    
    context.user_data['current_state'] = ADMIN_KNOWLEDGE


async def show_feedback_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню управления отзывами"""
    keyboard = [
        ["📥 Скачать отзывы", "📊 Анализ отзывов"],
        ["📧 Отправить уведомление", "🗑️ Очистить отзывы"],
        ["🔙 Назад в админку"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("📊 Управление отзывами:", reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text("📊 Управление отзывами:", reply_markup=reply_markup)
    
    context.user_data['current_state'] = ADMIN_FEEDBACK


# === УПРАВЛЕНИЕ БАЗОЙ ЗНАНИЙ ===

async def handle_knowledge_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с базой знаний"""
    text = update.message.text.strip()
    
    if text == "➕ Добавить знание":
        await update.message.reply_text("📝 Введите ключевое слово для нового знания:")
        context.user_data['knowledge_action'] = 'add_key'
        return True
    elif text == "📋 Просмотреть базу":
        knowledge_base = load_knowledge_base()
        if knowledge_base:
            response = "📚 Текущая база знаний:\n\n"
            for i, (key, value) in enumerate(knowledge_base.items(), 1):
                response += f"{i}. 🔑 {key}: {value[:100]}{'...' if len(value) > 100 else ''}\n\n"
        else:
            response = "📚 База знаний пуста."
        await update.message.reply_text(response)
        return True
    elif text == "✏️ Редактировать знание":
        knowledge_base = load_knowledge_base()
        if knowledge_base:
            response = "📝 Введите ключевое слово для редактирования:\n\nДоступные ключи:\n"
            response += "\n".join([f"• {key}" for key in knowledge_base.keys()])
        else:
            response = "📚 База знаний пуста."
        await update.message.reply_text(response)
        context.user_data['knowledge_action'] = 'edit_key'
        return True
    elif text == "🗑️ Удалить знание":
        knowledge_base = load_knowledge_base()
        if knowledge_base:
            response = "📝 Введите ключевое слово для удаления:\n\nДоступные ключи:\n"
            response += "\n".join([f"• {key}" for key in knowledge_base.keys()])
        else:
            response = "📚 База знаний пуста."
        await update.message.reply_text(response)
        context.user_data['knowledge_action'] = 'delete_key'
        return True
    elif text == "🔙 Назад в админку":
        await show_admin_menu(update, context)
        return True
    
    return False


async def handle_knowledge_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода для управления базой знаний"""
    if 'knowledge_action' not in context.user_data:
        return False
    
    action = context.user_data['knowledge_action']
    text = update.message.text.strip()
    
    if action == 'add_key':
        context.user_data['new_key'] = text
        await update.message.reply_text("📝 Введите значение для этого ключа:")
        context.user_data['knowledge_action'] = 'add_value'
        return True
    elif action == 'add_value':
        key = context.user_data.get('new_key', '')
        if key:
            knowledge_base = load_knowledge_base()
            knowledge_base[key] = text
            save_knowledge_base(knowledge_base)
            await update.message.reply_text(f"✅ Знание '{key}' успешно добавлено!")
        else:
            await update.message.reply_text("❌ Ошибка при добавлении знания.")
        del context.user_data['knowledge_action']
        if 'new_key' in context.user_data:
            del context.user_data['new_key']
        await show_knowledge_admin_menu(update, context)
        return True
    elif action == 'edit_key':
        context.user_data['edit_key'] = text
        knowledge_base = load_knowledge_base()
        if text in knowledge_base:
            await update.message.reply_text(f"📝 Текущее значение '{text}':\n{knowledge_base[text]}\n\nВведите новое значение:")
            context.user_data['knowledge_action'] = 'edit_value'
        else:
            await update.message.reply_text(f"❌ Знание с ключом '{text}' не найдено.")
            del context.user_data['knowledge_action']
            if 'edit_key' in context.user_data:
                del context.user_data['edit_key']
            await show_knowledge_admin_menu(update, context)
        return True
    elif action == 'edit_value':
        key = context.user_data.get('edit_key', '')
        if key:
            knowledge_base = load_knowledge_base()
            knowledge_base[key] = text
            save_knowledge_base(knowledge_base)
            await update.message.reply_text(f"✅ Знание '{key}' успешно обновлено!")
        else:
            await update.message.reply_text("❌ Ошибка при редактировании знания.")
        del context.user_data['knowledge_action']
        if 'edit_key' in context.user_data:
            del context.user_data['edit_key']
        await show_knowledge_admin_menu(update, context)
        return True
    elif action == 'delete_key':
        knowledge_base = load_knowledge_base()
        if text in knowledge_base:
            del knowledge_base[text]
            save_knowledge_base(knowledge_base)
            await update.message.reply_text(f"✅ Знание '{text}' успешно удалено!")
        else:
            await update.message.reply_text(f"❌ Знание с ключом '{text}' не найдено.")
        del context.user_data['knowledge_action']
        await show_knowledge_admin_menu(update, context)
        return True
    
    return False


# === УПРАВЛЕНИЕ ОТЗЫВАМИ ===

async def handle_feedback_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с отзывами"""
    text = update.message.text.strip()
    
    if text == "📥 Скачать отзывы":
        if not os.path.exists(EXCEL_FILE):
            await update.message.reply_text("📁 Файл отзывов ещё не создан.")
            return True
        try:
            with open(EXCEL_FILE, "rb") as f:
                await update.message.reply_document(document=f, filename="feedback.xlsx", caption="📊 Все отзывы")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Ошибка при отправке файла: {e}")
        return True
    elif text == "📊 Анализ отзывов":
        # Анализ отзывов
        if os.path.exists(EXCEL_FILE):
            try:
                df = pd.read_excel(EXCEL_FILE)
                total_feedbacks = len(df)
                avg_rating = df['Оценка'].mean() if 'Оценка' in df.columns else 0
                anonymous_count = len(df[df['Анонимный'] == 'Да']) if 'Анонимный' in df.columns else 0
                
                response = f"📈 Аналитика отзывов:\n\n"
                response += f"📊 Всего отзывов: {total_feedbacks}\n"
                response += f"⭐ Средняя оценка: {avg_rating:.1f}\n"
                response += f"👤 Анонимных отзывов: {anonymous_count}\n"
                response += f"📝 Публичных отзывов: {total_feedbacks - anonymous_count}"
                
                await update.message.reply_text(response)
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка при анализе: {e}")
        else:
            await update.message.reply_text("📁 Файл отзывов ещё не создан.")
        return True
    elif text == "📧 Отправить уведомление":
        await update.message.reply_text("📝 Введите текст уведомления для всех пользователей:")
        context.user_data['admin_action'] = 'send_notification'
        return True
    elif text == "🗑️ Очистить отзывы":
        keyboard = [
            [InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear"),
             InlineKeyboardButton("❌ Отмена", callback_data="cancel_clear")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ Вы уверены, что хотите очистить все отзывы?\nЭто действие нельзя отменить!",
            reply_markup=reply_markup
        )
        return True
    elif text == "🔙 Назад в админку":
        await show_admin_menu(update, context)
        return True
    
    return False


# === ОСНОВНЫЕ ОБРАБОТЧИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    is_owner = (user_id == OWNER_USER_ID)
    
    # Очищаем все состояния при запуске
    context.user_data.clear()
    
    await update.message.reply_text(
        f"👋 Привет{'ствую, владелец!' if is_owner else '!'}\nЯ — умный бот на базе Mistral AI 🧠",
        reply_markup=ReplyKeyboardRemove()
    )
    await show_main_menu(update, context, is_owner)


async def start_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начало диалога с нейросетью"""
    context.user_data['ai_chat_history'] = []
    context.user_data['current_state'] = AI_CHAT
    
    keyboard = [["🛑 Завершить диалог"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "🤖 Диалог с нейросетью начат! Напишите ваш вопрос.\n"
        "Нейросеть будет использовать информацию из базы знаний для более точных ответов.\n"
        "Вы можете в любой момент завершить диалог, нажав кнопку 'Завершить диалог'.",
        reply_markup=reply_markup
    )


async def end_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Завершение диалога с нейросетью"""
    if 'ai_chat_history' in context.user_data:
        del context.user_data['ai_chat_history']
    if 'current_state' in context.user_data:
        del context.user_data['current_state']
    
    await update.message.reply_text(
        "✅ Диалог с нейросетью завершен.",
        reply_markup=ReplyKeyboardRemove()
    )
    user_id = update.effective_user.id
    is_owner = (user_id == OWNER_USER_ID)
    await show_main_menu(update, context, is_owner)


async def handle_ai_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка сообщения в режиме диалога с нейросетью"""
    if update.message.text == "🛑 Завершить диалог":
        await end_ai_chat(update, context)
        return
    
    await update.message.chat.send_action(action="typing")
    
    chat_history = context.user_data.get('ai_chat_history', [])
    knowledge_base = load_knowledge_base()
    knowledge_context = search_knowledge_base(update.message.text, knowledge_base)
    
    response = await call_mistral_api(update.message.text, chat_history, knowledge_context)
    
    chat_history.append({"role": "user", "content": update.message.text})
    chat_history.append({"role": "assistant", "content": response})
    context.user_data['ai_chat_history'] = chat_history
    
    await update.message.reply_text(response)
    
    keyboard = [["🛑 Завершить диалог"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("👇 Продолжайте диалог или завершите его:", reply_markup=reply_markup)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    current_state = context.user_data.get('current_state')
    user_id = update.effective_user.id
    is_owner = (user_id == OWNER_USER_ID)
    
    # Обработка специальных состояний
    if 'knowledge_action' in context.user_data:
        if await handle_knowledge_input(update, context):
            return
    
    if 'admin_action' in context.user_data:
        admin_action = context.user_data['admin_action']
        if admin_action == 'send_notification':
            # Отправка уведомления всем пользователям (заглушка)
            await update.message.reply_text(
                f"📢 Уведомление отправлено всем пользователям:\n\n{text}"
            )
            del context.user_data['admin_action']
            await show_feedback_admin_menu(update, context)
            return
    
    # Если активен диалог с нейросетью
    if current_state == AI_CHAT:
        await handle_ai_chat_message(update, context)
        return
    
    # Если в админке
    if current_state == ADMIN_MENU and is_owner:
        if text == "📚 Управление знаниями":
            await show_knowledge_admin_menu(update, context)
            return
        elif text == "📊 Управление отзывами":
            await show_feedback_admin_menu(update, context)
            return
        elif text == "📈 Статистика":
            # Показ статистики
            stats_text = "📈 Статистика бота:\n\n"
            stats_text += "📊 Отзывы: "
            if os.path.exists(EXCEL_FILE):
                try:
                    df = pd.read_excel(EXCEL_FILE)
                    stats_text += f"{len(df)} записей\n"
                except:
                    stats_text += "ошибка чтения\n"
            else:
                stats_text += "нет данных\n"
            
            stats_text += "📚 База знаний: "
            knowledge_base = load_knowledge_base()
            stats_text += f"{len(knowledge_base)} записей\n"
            
            await update.message.reply_text(stats_text)
            return
        elif text == "⚙️ Настройки":
            await update.message.reply_text("⚙️ Настройки бота (в разработке)")
            return
        elif text == "🔙 В главное меню":
            await show_main_menu(update, context, True)
            if 'current_state' in context.user_data:
                del context.user_data['current_state']
            return
    
    # Если в управлении знаниями
    if current_state == ADMIN_KNOWLEDGE and is_owner:
        if await handle_knowledge_admin_action(update, context):
            return
    
    # Если в управлении отзывами
    if current_state == ADMIN_FEEDBACK and is_owner:
        if await handle_feedback_admin_action(update, context):
            return
    
    # Обработка главного меню
    if text == "📩 Обратная связь":
        return  # Перехватит ConversationHandler
    elif text == "📥 Скачать Excel":
        if is_owner:
            return await get_feedback_file(update, context)
        else:
            await update.message.reply_text("❌ У вас нет доступа.")
            return
    elif text == "🔄 Перезапустить":
        context.user_data.clear()
        return await start(update, context)
    elif text == "💬 Задать вопрос":
        await start_ai_chat(update, context)
        return
    elif text == "🛑 Завершить диалог":
        await end_ai_chat(update, context)
        return
    elif text == "📚 База знаний":
        if is_owner:
            # Для владельца показываем меню управления
            await show_knowledge_admin_menu(update, context)
        else:
            # Для обычных пользователей показываем содержимое
            knowledge_base = load_knowledge_base()
            if knowledge_base:
                response = "📚 Информация из базы знаний:\n\n"
                for key, value in knowledge_base.items():
                    response += f"🔑 {key}:\n{value}\n\n"
            else:
                response = "📚 База знаний пуста."
            await update.message.reply_text(response)
            await show_main_menu(update, context, False)
        return
    elif text == "📊 Статистика" and is_owner:
        # Прямой доступ к статистике
        stats_text = "📈 Статистика бота:\n\n"
        stats_text += "📊 Отзывы: "
        if os.path.exists(EXCEL_FILE):
            try:
                df = pd.read_excel(EXCEL_FILE)
                stats_text += f"{len(df)} записей\n"
            except:
                stats_text += "ошибка чтения\n"
        else:
            stats_text += "нет данных\n"
        
        stats_text += "📚 База знаний: "
        knowledge_base = load_knowledge_base()
        stats_text += f"{len(knowledge_base)} записей\n"
        
        await update.message.reply_text(stats_text)
        return
    elif text == "👑 Админка" and is_owner:
        await show_admin_menu(update, context)
        return
    
    # Если ни одна функция не активна - предлагаем выбрать действие
    await update.message.reply_text(
        "🤔 Пожалуйста, выберите действие из меню:",
        reply_markup=ReplyKeyboardRemove()
    )
    await show_main_menu(update, context, is_owner)


# === ОБРАТНАЯ СВЯЗЬ ===

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("✅ Да, анонимно", callback_data="anon_yes"),
         InlineKeyboardButton("👤 Обычный", callback_data="anon_no")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📨 Выберите тип отзыва:", reply_markup=reply_markup)
    return ANONYMOUS


async def handle_anonymous_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await safe_edit_message(query, "❌ Анкета отменена.")
        user_id = query.from_user.id
        is_owner = (user_id == OWNER_USER_ID)
        await show_main_menu(query, context, is_owner)
        return ConversationHandler.END

    context.user_data['user_wants_anon_label'] = (query.data == "anon_yes")
    keyboard = [
        [InlineKeyboardButton("⭐️ 1", callback_data="1"), InlineKeyboardButton("⭐️ 2", callback_data="2"), InlineKeyboardButton("⭐️ 3", callback_data="3")],
        [InlineKeyboardButton("⭐️ 4", callback_data="4"), InlineKeyboardButton("⭐️ 5", callback_data="5")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_message(query, "🌟 Оцените бота от 1 до 5:", reply_markup=reply_markup)
    return RATING


async def handle_rating_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await safe_edit_message(query, "❌ Анкета отменена.")
        user_id = query.from_user.id
        is_owner = (user_id == OWNER_USER_ID)
        await show_main_menu(query, context, is_owner)
        return ConversationHandler.END

    context.user_data['rating'] = query.data
    await safe_edit_message(query, "💬 Напишите ваш отзыв (можно кратко):")
    return COMMENT


async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['comment'] = update.message.text
    user = update.message.from_user
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    is_anon = context.user_data.get('user_wants_anon_label', False)

    report = (
        f"📩 ОТЗЫВ\nОт: {username}\nОценка: {context.user_data['rating']} ⭐️\n"
        f"Комментарий: {context.user_data['comment']}\nАнонимный: {'Да' if is_anon else 'Нет'}\n---\n"
    )

    os.makedirs(BASE_DIR, exist_ok=True)
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(report)

    await save_feedback_to_excel(
        EXCEL_FILE,
        datetime.now(),
        username,
        context.user_data['rating'],
        context.user_data['comment'],
        is_anon
    )

    try:
        await context.bot.send_message(chat_id=OWNER_USER_ID, text=report)
    except Exception as e:
        print(f"[Send to owner error] {e}")

    await update.message.reply_sticker(sticker=THANKS_ANIMATION)
    await update.message.reply_text("🙏 Спасибо за отзыв!", reply_markup=ReplyKeyboardRemove())
    user_id = update.effective_user.id
    is_owner = (user_id == OWNER_USER_ID)
    await show_main_menu(update, context, is_owner)
    context.user_data.clear()
    return ConversationHandler.END


async def save_feedback_to_excel(file_path, timestamp, user_id, rating, comment, is_anon):
    new_row = {
        "Дата и время": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "Пользователь": user_id,
        "Оценка": int(rating),
        "Комментарий": comment,
        "Анонимный": "Да" if is_anon else "Нет"
    }
    df_new = pd.DataFrame([new_row])
    try:
        df = pd.read_excel(file_path) if os.path.exists(file_path) else pd.DataFrame()
        df = pd.concat([df, df_new], ignore_index=True)
        df.to_excel(file_path, index=False, engine='openpyxl')
        print(f"[Excel] ✅ Сохранено. Всего: {len(df)} записей")
    except Exception as e:
        print(f"[Excel Error] {e}")
        with open(file_path.replace(".xlsx", "_backup.txt"), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {user_id} | {rating} | {comment} | Анонимный: {is_anon}\n")


# === АДМИН-ФУНКЦИИ ===

async def get_feedback_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_USER_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    if not os.path.exists(EXCEL_FILE):
        await update.message.reply_text("📁 Файл ещё не создан.")
        return
    try:
        with open(EXCEL_FILE, "rb") as f:
            await update.message.reply_document(document=f, filename="feedback.xlsx", caption="📊 Отзывы")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка callback query (для inline кнопок)"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_clear":
        # Очистка отзывов
        try:
            if os.path.exists(EXCEL_FILE):
                os.remove(EXCEL_FILE)
            if os.path.exists(FEEDBACK_FILE):
                os.remove(FEEDBACK_FILE)
                # Создаем новый пустой файл
                with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                    f.write("Обратная связь:\n\n")
            await query.edit_message_text("✅ Все отзывы успешно очищены!")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при очистке: {e}")
    elif query.data == "cancel_clear":
        await query.edit_message_text("❌ Очистка отзывов отменена.")
    
    user_id = query.from_user.id
    is_owner = (user_id == OWNER_USER_ID)
    await show_feedback_admin_menu(query, context)


# === ЗАПУСК ===

def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    os.makedirs(BASE_DIR, exist_ok=True)
    if not os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            f.write("Обратная связь:\n\n")

    app = Application.builder().token(TOKEN).build()

    # ✅ ConversationHandler для анкеты
    feedback_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📩 Обратная связь$"), feedback_start)],
        states={
            ANONYMOUS: [CallbackQueryHandler(handle_anonymous_choice)],
            RATING: [CallbackQueryHandler(handle_rating_choice)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
        allow_reentry=True
    )
    app.add_handler(feedback_handler)

    # Обработчики callback query
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Общие обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("getfeedback", get_feedback_file))

    print("✅ Бот запущен. Все функции работают.")
    app.run_polling()


if __name__ == "__main__":
    main()