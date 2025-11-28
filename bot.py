import os
import asyncio
import logging
import json
from datetime import datetime, timedelta

try:
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.filters import Command
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import BotCommand, BotCommandScopeDefault
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Установите зависимости: pip install aiogram apscheduler python-dotenv")
    exit(1)

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 Токен бота теперь берется из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")

# Проверка токена
if not TOKEN:
    logger.error("❌ Токен бота не найден! Убедитесь, что файл .env существует и содержит BOT_TOKEN")
    print("❌ Токен бота не найден!")
    print("📝 Создайте файл .env в той же папке, что и bot.py")
    print("📝 Добавьте в него: BOT_TOKEN=ваш_токен_от_botfather")
    exit(1)

# ID группы для отправки расписания
GROUP_CHAT_ID = None

# ⚡ ВПИШИТЕ СЮДА ID ВАШИХ АДМИНИСТРАТОРОВ ⚡
ADMIN_IDS = {5810097604}  # Замените эти числа на реальные ID администраторов

# Для хранения ID закрепленных сообщений
pinned_messages = {}

# Файлы для хранения данных
SCHEDULE_FILE = "schedule.json"
CONFIG_FILE = "config.json"

# Загрузка данных из файлов
def load_data():
    global schedule, START_DATE
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                schedule = data.get('schedule', {})
                START_DATE = datetime.fromisoformat(data.get('start_date', '2024-09-01'))
        else:
            # Значения по умолчанию
            schedule = {
                "понедельник": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "вторник": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "среда": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "четверг": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "пятница": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "суббота": "📅 Суббота — выходной 😴",
                "воскресенье": "📅 Воскресенье — выходной 😴"
            }
            START_DATE = datetime(2024, 9, 1)
        
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                ADMIN_IDS.update(set(config.get('admin_ids', [])))
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        schedule = {}
        START_DATE = datetime(2024, 9, 1)

# Сохранение данных в файлы
def save_data():
    try:
        # Сохраняем расписание
        with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'schedule': schedule,
                'start_date': START_DATE.isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        # Сохраняем конфигурацию
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'admin_ids': list(ADMIN_IDS)
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# Определяем текущую неделю
def get_current_week():
    now = datetime.now()
    delta = now - START_DATE
    week_number = delta.days // 7
    return "верхняя" if week_number % 2 == 0 else "нижняя"

# Инициализация бота
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

async def set_bot_commands():
    """Установка команд меню бота"""
    commands = [
        BotCommand(command="start", description="Настройка бота"),
        BotCommand(command="id", description="Узнать свой ID"),
        BotCommand(command="today", description="Расписание на сегодня"),
        BotCommand(command="tomorrow", description="Расписание на завтра"),
        BotCommand(command="week", description="Какая сейчас неделя"),
        BotCommand(command="monday", description="Расписание на понедельник"),
        BotCommand(command="tuesday", description="Расписание на вторник"),
        BotCommand(command="wednesday", description="Расписание на среду"),
        BotCommand(command="thursday", description="Расписание на четверг"),
        BotCommand(command="friday", description="Расписание на пятницу"),
        BotCommand(command="saturday", description="Расписание на субботу"),
        BotCommand(command="sunday", description="Расписание на воскресенье"),
        BotCommand(command="announce", description="Создать объявление (админы)"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Команды бота успешно установлены")
    except Exception as e:
        logger.error(f"Ошибка установки команд: {e}")

async def unpin_previous_message():
    """Открепляет и удаляет предыдущее сообщение с расписанием"""
    if GROUP_CHAT_ID and pinned_messages.get(GROUP_CHAT_ID):
        try:
            message_id = pinned_messages[GROUP_CHAT_ID]
            await bot.unpin_chat_message(GROUP_CHAT_ID, message_id)
            await bot.delete_message(GROUP_CHAT_ID, message_id)
            logger.info(f"Сообщение {message_id} откреплено и удалено")
            pinned_messages[GROUP_CHAT_ID] = None
        except Exception as e:
            logger.error(f"Ошибка при откреплении сообщения: {e}")

async def send_daily_schedule():
    """Отправляет расписание на текущий день в группу и закрепляет его"""
    if not GROUP_CHAT_ID:
        logger.warning("GROUP_CHAT_ID не установлен")
        return
    
    # Открепляем предыдущее сообщение
    await unpin_previous_message()
    
    today = datetime.now().strftime("%A").lower()
    days_map = {
        "monday": "понедельник",
        "tuesday": "вторник",
        "wednesday": "среда",
        "thursday": "четверг",
        "friday": "пятница",
        "saturday": "суббота",
        "sunday": "воскресенье"
    }
    
    day_rus = days_map.get(today)
    if not day_rus:
        return
    
    week_type = get_current_week()
    
    if day_rus in ["суббота", "воскресенье"]:
        text = schedule.get(day_rus, "❌ Расписание на этот день не настроено")
    else:
        day_schedule = schedule.get(day_rus)
        if day_schedule and isinstance(day_schedule, dict):
            text = day_schedule.get(week_type, "❌ Расписание на эту неделю не настроено")
        else:
            text = "❌ Расписание на этот день не настроено"
    
    try:
        message = f"<b>📅 РАСПИСАНИЕ НА СЕГОДНЯ</b>\n\n{text}\n\n<i>Автоматическое сообщение • {datetime.now().strftime('%d.%m.%Y')}</i>"
        sent_message = await bot.send_message(GROUP_CHAT_ID, message)
        
        # Закрепляем сообщение
        await bot.pin_chat_message(GROUP_CHAT_ID, sent_message.message_id)
        pinned_messages[GROUP_CHAT_ID] = sent_message.message_id
        
        logger.info(f"Расписание отправлено и закреплено для {day_rus} ({week_type} неделя)")
    except Exception as e:
        logger.error(f"Ошибка при отправке расписания: {e}")

def get_schedule_for_day(day: str, week_type: str = None):
    """Получить расписание для указанного дня"""
    if not week_type:
        week_type = get_current_week()
    
    if day in ["суббота", "воскресенье"]:
        return schedule.get(day, "❌ Расписание не настроено")
    else:
        day_schedule = schedule.get(day)
        if day_schedule and isinstance(day_schedule, dict):
            return day_schedule.get(week_type, "❌ Расписание не настроено")
        return "❌ Расписание не настроено"

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    """Команда для установки группы"""
    global GROUP_CHAT_ID
    if message.chat.type in ["group", "supergroup"]:
        GROUP_CHAT_ID = message.chat.id
        
        # Сохраняем ID группы в конфиг
        save_data()
        
        user_id = message.from_user.id
        await message.answer(
            f"✅ <b>Бот настроен для этой группы!</b>\n\n"
            f"• <b>Ваш ID:</b> {user_id}\n"
            f"• <b>Расписание:</b> ежедневно в 7:00\n"
            f"• <b>Сообщения:</b> автоматически закрепляются\n"
            f"• <b>Команды:</b> используйте меню слева от поля ввода\n\n"
            f"<i>Администраторы могут использовать /upload_schedule и /announce</i>"
        )
    else:
        await message.answer("Добавьте меня в группу и используйте /start для настройки")

@dp.message(Command(commands=["id"]))
async def get_user_id(message: types.Message):
    """Показать ID пользователя"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    await message.answer(f"🆔 <b>Ваш ID:</b> {user_id}\n<b>ID чата:</b> {chat_id}")

@dp.message(Command(commands=["today"]))
async def send_today_schedule(message: types.Message):
    """Расписание на сегодня"""
    today = datetime.now().strftime("%A").lower()
    days_map = {
        "monday": "понедельник", "tuesday": "вторник", "wednesday": "среда",
        "thursday": "четверг", "friday": "пятница", "saturday": "суббота", 
        "sunday": "воскресенье"
    }
    
    day_rus = days_map.get(today, "понедельник")
    week_type = get_current_week()
    text = get_schedule_for_day(day_rus, week_type)
    
    message_text = f"<b>📅 РАСПИСАНИЕ НА СЕГОДНЯ</b>\n({day_rus.capitalize()}, {week_type} неделя)\n\n{text}"
    await message.answer(message_text)

@dp.message(Command(commands=["tomorrow"]))
async def send_tomorrow_schedule(message: types.Message):
    """Расписание на завтра"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A").lower()
    days_map = {
        "monday": "понедельник", "tuesday": "вторник", "wednesday": "среда",
        "thursday": "четверг", "friday": "пятница", "saturday": "суббота", 
        "sunday": "воскресенье"
    }
    
    day_rus = days_map.get(tomorrow, "понедельник")
    week_type = get_current_week()
    # Для завтрашнего дня меняем тип недели
    tomorrow_week_type = "нижняя" if week_type == "верхняя" else "верхняя"
    text = get_schedule_for_day(day_rus, tomorrow_week_type)
    
    message_text = f"<b>📅 РАСПИСАНИЕ НА ЗАВТРА</b>\n({day_rus.capitalize()}, {tomorrow_week_type} неделя)\n\n{text}"
    await message.answer(message_text)

@dp.message(Command(commands=["week"]))
async def send_week_info(message: types.Message):
    """Какая сейчас неделя"""
    week_type = get_current_week()
    next_week_type = "нижняя" if week_type == "верхняя" else "верхняя"
    
    await message.answer(
        f"<b>📊 ИНФОРМАЦИЯ О НЕДЕЛЕ</b>\n\n"
        f"• <b>Текущая неделя:</b> {week_type.capitalize()}\n"
        f"• <b>Следующая неделя:</b> {next_week_type.capitalize()}\n"
        f"• <b>Начало семестра:</b> {START_DATE.strftime('%d.%m.%Y')}\n"
        f"• <b>Сегодня:</b> {datetime.now().strftime('%d.%m.%Y')}"
    )

@dp.message(Command(commands=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]))
async def send_schedule(message: types.Message):
    """Ручная команда для получения расписания"""
    day_en = message.text.replace("/", "").lower()
    days_map = {
        "monday": "понедельник",
        "tuesday": "вторник", 
        "wednesday": "среда",
        "thursday": "четверг",
        "friday": "пятница",
        "saturday": "суббота",
        "sunday": "воскресенье"
    }
    
    day_rus = days_map.get(day_en, day_en)
    week_type = get_current_week()
    
    text = get_schedule_for_day(day_rus, week_type)
    next_week_type = "нижняя" if week_type == "верхняя" else "верхняя"
    next_week_text = get_schedule_for_day(day_rus, next_week_type)
    
    message_text = f"<b>📅 РАСПИСАНИЕ НА {day_rus.upper()}</b>\n\n"
    message_text += f"<b>{week_type.capitalize()} неделя:</b>\n{text}\n\n"
    
    if day_rus not in ["суббота", "воскресенье"]:
        message_text += f"<b>{next_week_type.capitalize()} неделя:</b>\n{next_week_text}"
    
    await message.answer(message_text)

@dp.message(Command(commands=["announce"]))
async def create_announcement(message: types.Message):
    """Создание объявления с @everyone в конце"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer(f"❌ Только администраторы могут создавать объявления!\nВаш ID: {user_id}")
        return
    
    announcement_text = message.text.replace("/announce", "").strip()
    if not announcement_text:
        await message.answer("❌ Укажите текст объявления после команды /announce")
        return
    
    announcement_message = f"<b>📢 ОБЪЯВЛЕНИЕ</b>\n\n{announcement_text}\n\n@everyone"
    
    try:
        sent_message = await message.answer(announcement_message)
        
        # Закрепляем объявление
        await bot.pin_chat_message(message.chat.id, sent_message.message_id)
        logger.info(f"Объявление создано и закреплено администратором {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке объявления: {e}")
        await message.answer("❌ Произошла ошибка при создании объявления")

@dp.message(Command(commands=["upload_schedule"]))
async def upload_schedule(message: types.Message):
    """Загрузка расписания администратором"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут загружать расписание!")
        return
    
    help_text = """
<b>📝 ЗАГРУЗКА РАСПИСАНИЯ</b>

Отправьте расписание в формате:

<code>/set_schedule monday upper
1. Предмет (Преподаватель, кабинет)
2. Предмет (Преподаватель, кабинет)
...</code>

Или для выходных:
<code>/set_schedule saturday
Выходной день</code>

Доступные дни: monday, tuesday, wednesday, thursday, friday, saturday, sunday
Типы недель: upper, lower
    """
    
    await message.answer(help_text)

@dp.message(Command(commands=["set_schedule"]))
async def set_schedule(message: types.Message):
    """Установка расписания для конкретного дня и недели"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут устанавливать расписание!")
        return
    
    try:
        parts = message.text.split('\n', 1)
        if len(parts) < 2:
            await message.answer("❌ Неправильный формат. Используйте:\n/set_schedule day week\nрасписание...")
            return
        
        header = parts[0].replace("/set_schedule", "").strip()
        schedule_text = parts[1].strip()
        
        header_parts = header.split()
        if len(header_parts) < 1:
            await message.answer("❌ Укажите день недели")
            return
        
        day_en = header_parts[0].lower()
        days_map = {
            "monday": "понедельник",
            "tuesday": "вторник",
            "wednesday": "среда", 
            "thursday": "четверг",
            "friday": "пятница",
            "saturday": "суббота",
            "sunday": "воскресенье"
        }
        
        day_rus = days_map.get(day_en)
        if not day_rus:
            await message.answer(f"❌ Неправильный день. Доступные: {', '.join(days_map.keys())}")
            return
        
        # Для выходных дней
        if day_rus in ["суббота", "воскресенье"]:
            schedule[day_rus] = schedule_text
            save_data()
            await message.answer(f"✅ Расписание для {day_rus} установлено!")
            return
        
        # Для учебных дней
        if len(header_parts) < 2:
            await message.answer("❌ Для учебных дней укажите тип недели (upper/lower)")
            return
        
        week_type_en = header_parts[1].lower()
        week_type_map = {
            "upper": "верхняя",
            "lower": "нижняя"
        }
        
        week_type_rus = week_type_map.get(week_type_en)
        if not week_type_rus:
            await message.answer("❌ Тип недели должен быть 'upper' или 'lower'")
            return
        
        if day_rus not in schedule:
            schedule[day_rus] = {}
        
        schedule[day_rus][week_type_rus] = schedule_text
        save_data()
        await message.answer(f"✅ Расписание для {day_rus} ({week_type_rus} неделя) установлено!")
        
    except Exception as e:
        logger.error(f"Ошибка установки расписания: {e}")
        await message.answer("❌ Произошла ошибка при установке расписания")

@dp.message(Command(commands=["admins"]))
async def show_admins(message: types.Message):
    """Показать список администраторов"""
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        admins_list = "\n".join([f"• {admin_id}" for admin_id in ADMIN_IDS])
        await message.answer(f"<b>📋 Текущие администраторы:</b>\n{admins_list}\n\n<b>Ваш ID:</b> {user_id}")
    else:
        await message.answer(f"❌ У вас нет прав для этой команды\nВаш ID: {user_id}")

@dp.message(Command(commands=["add_admin"]))
async def add_admin(message: types.Message):
    """Добавить администратора (только для существующих админов)"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут добавлять других админов!")
        return
    
    try:
        new_admin_id = int(message.text.split()[1])
        ADMIN_IDS.add(new_admin_id)
        save_data()
        await message.answer(f"✅ ID {new_admin_id} добавлен в администраторы!")
        logger.info(f"Добавлен новый администратор: {new_admin_id}")
    except (IndexError, ValueError):
        await message.answer("❌ Используйте: /add_admin <ID_пользователя>")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command(commands=["remove_admin"]))
async def remove_admin(message: types.Message):
    """Удалить администратора"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут использовать эту команду!")
        return
    
    try:
        target_id = int(message.text.split()[1])
        if target_id == user_id:
            await message.answer("❌ Вы не можете удалить сами себя!")
            return
        
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)
            save_data()
            await message.answer(f"✅ ID {target_id} удален из администраторов!")
        else:
            await message.answer("❌ Этот пользователь не является администратором")
    except (IndexError, ValueError):
        await message.answer("❌ Используйте: /remove_admin <ID_пользователя>")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command(commands=["clear_schedule"]))
async def clear_schedule(message: types.Message):
    """Очистить все расписание"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут очищать расписание!")
        return
    
    try:
        global schedule
        schedule = {
            "понедельник": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
            "вторник": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
            "среда": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
            "четверг": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
            "пятница": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
            "суббота": "📅 Суббота — выходной 😴",
            "воскресенье": "📅 Воскресенье — выходной 😴"
        }
        save_data()
        await message.answer("✅ Все расписание очищено!")
    except Exception as e:
        await message.answer(f"❌ Ошибка при очистке: {e}")

async def on_startup():
    """Запуск планировщика при старте бота"""
    load_data()
    await set_bot_commands()
    
    # Расписание на 7:00 утра
    scheduler.add_job(send_daily_schedule, CronTrigger(hour=7, minute=0))
    scheduler.start()
    
    logger.info("Бот запущен и готов к работе!")
    logger.info(f"Загружены администраторы: {ADMIN_IDS}")
    logger.info(f"Текущая неделя: {get_current_week()}")

async def on_shutdown():
    """Остановка планировщика при выключении бота"""
    scheduler.shutdown()
    logger.info("Бот остановлен")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())