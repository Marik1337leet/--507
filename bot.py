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

# ⚡ ВПИШИТЕ СЮДА ID ВАШИХ АДМИНИСТРАТОРОВ ⚡
ADMIN_IDS = {5810097604}  # Замените эти числа на реальные ID администраторов

# Для хранения ID закрепленных сообщений
pinned_messages = {}

# Файлы для хранения данных
GROUPS_FILE = "groups.json"
CONFIG_FILE = "config.json"

# Структура данных для групп
groups_data = {}

# Загрузка данных из файлов
def load_data():
    global groups_data, ADMIN_IDS
    try:
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                groups_data = json.load(f)
        
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                ADMIN_IDS.update(set(config.get('admin_ids', [])))
                
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        groups_data = {}

# Сохранение данных в файлы
def save_data():
    try:
        # Сохраняем данные групп
        with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(groups_data, f, ensure_ascii=False, indent=2)
        
        # Сохраняем конфигурацию
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'admin_ids': list(ADMIN_IDS)
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

def init_group_data(chat_id):
    """Инициализирует данные для новой группы"""
    if str(chat_id) not in groups_data:
        groups_data[str(chat_id)] = {
            "start_date": "2024-09-01",
            "schedule": {
                "понедельник": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "вторник": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "среда": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "четверг": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "пятница": {"верхняя": "❌ Расписание не настроено", "нижняя": "❌ Расписание не настроено"},
                "суббота": "📅 Суббота — выходной 😴",
                "воскресенье": "📅 Воскресенье — выходной 😴"
            },
            "admins": [],
            "created_at": datetime.now().isoformat()
        }
        save_data()
        return True
    return False

def get_group_schedule(chat_id):
    """Получает расписание для конкретной группы"""
    return groups_data.get(str(chat_id), {}).get("schedule", {})

def get_group_start_date(chat_id):
    """Получает дату начала семестра для группы"""
    group_data = groups_data.get(str(chat_id), {})
    start_date_str = group_data.get("start_date", "2024-09-01")
    return datetime.fromisoformat(start_date_str)

def get_current_week(chat_id):
    """Определяет текущую неделю для группы"""
    start_date = get_group_start_date(chat_id)
    now = datetime.now()
    delta = now - start_date
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
        BotCommand(command="upload_schedule", description="Загрузить расписание (админы)"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Команды бота успешно установлены")
    except Exception as e:
        logger.error(f"Ошибка установки команд: {e}")

async def unpin_previous_message(chat_id):
    """Открепляет и удаляет предыдущее сообщение с расписанием"""
    if pinned_messages.get(chat_id):
        try:
            message_id = pinned_messages[chat_id]
            await bot.unpin_chat_message(chat_id, message_id)
            await bot.delete_message(chat_id, message_id)
            logger.info(f"Сообщение {message_id} откреплено и удалено для чата {chat_id}")
            pinned_messages[chat_id] = None
        except Exception as e:
            logger.error(f"Ошибка при откреплении сообщения: {e}")

async def send_daily_schedule():
    """Отправляет расписание на текущий день во все группы и закрепляет его"""
    for chat_id_str in groups_data.keys():
        chat_id = int(chat_id_str)
        
        # Открепляем предыдущее сообщение
        await unpin_previous_message(chat_id)
        
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
            continue
        
        week_type = get_current_week(chat_id)
        schedule = get_group_schedule(chat_id)
        
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
            sent_message = await bot.send_message(chat_id, message)
            
            # Закрепляем сообщение
            await bot.pin_chat_message(chat_id, sent_message.message_id)
            pinned_messages[chat_id] = sent_message.message_id
            
            logger.info(f"Расписание отправлено и закреплено для чата {chat_id} - {day_rus} ({week_type} неделя)")
        except Exception as e:
            logger.error(f"Ошибка при отправке расписания в чат {chat_id}: {e}")

def get_schedule_for_day(chat_id, day: str, week_type: str = None):
    """Получить расписание для указанного дня"""
    if not week_type:
        week_type = get_current_week(chat_id)
    
    schedule = get_group_schedule(chat_id)
    
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
    if message.chat.type in ["group", "supergroup"]:
        is_new_group = init_group_data(message.chat.id)
        
        user_id = message.from_user.id
        response = f"✅ <b>Бот настроен для этой группы!</b>\n\n"
        
        if is_new_group:
            response += "🎉 <b>Создана новая база данных для группы</b>\n"
        
        response += (
            f"• <b>ID группы:</b> {message.chat.id}\n"
            f"• <b>Ваш ID:</b> {user_id}\n"
            f"• <b>Расписание:</b> ежедневно в 7:00\n"
            f"• <b>Сообщения:</b> автоматически закрепляются\n"
            f"• <b>Команды:</b> используйте меню слева от поля ввода\n\n"
            f"<i>Администраторы могут использовать /upload_schedule для загрузки расписания</i>"
        )
        
        await message.answer(response)
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
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    init_group_data(message.chat.id)
    
    today = datetime.now().strftime("%A").lower()
    days_map = {
        "monday": "понедельник", "tuesday": "вторник", "wednesday": "среда",
        "thursday": "четверг", "friday": "пятница", "saturday": "суббота", 
        "sunday": "воскресенье"
    }
    
    day_rus = days_map.get(today, "понедельник")
    week_type = get_current_week(message.chat.id)
    text = get_schedule_for_day(message.chat.id, day_rus, week_type)
    
    message_text = f"<b>📅 РАСПИСАНИЕ НА СЕГОДНЯ</b>\n({day_rus.capitalize()}, {week_type} неделя)\n\n{text}"
    await message.answer(message_text)

@dp.message(Command(commands=["tomorrow"]))
async def send_tomorrow_schedule(message: types.Message):
    """Расписание на завтра"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    init_group_data(message.chat.id)
    
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A").lower()
    days_map = {
        "monday": "понедельник", "tuesday": "вторник", "wednesday": "среда",
        "thursday": "четверг", "friday": "пятница", "saturday": "суббота", 
        "sunday": "воскресенье"
    }
    
    day_rus = days_map.get(tomorrow, "понедельник")
    week_type = get_current_week(message.chat.id)
    # Для завтрашнего дня меняем тип недели
    tomorrow_week_type = "нижняя" if week_type == "верхняя" else "верхняя"
    text = get_schedule_for_day(message.chat.id, day_rus, tomorrow_week_type)
    
    message_text = f"<b>📅 РАСПИСАНИЕ НА ЗАВТРА</b>\n({day_rus.capitalize()}, {tomorrow_week_type} неделя)\n\n{text}"
    await message.answer(message_text)

@dp.message(Command(commands=["week"]))
async def send_week_info(message: types.Message):
    """Какая сейчас неделя"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    init_group_data(message.chat.id)
    
    week_type = get_current_week(message.chat.id)
    next_week_type = "нижняя" if week_type == "верхняя" else "верхняя"
    start_date = get_group_start_date(message.chat.id)
    
    await message.answer(
        f"<b>📊 ИНФОРМАЦИЯ О НЕДЕЛЕ</b>\n\n"
        f"• <b>Текущая неделя:</b> {week_type.capitalize()}\n"
        f"• <b>Следующая неделя:</b> {next_week_type.capitalize()}\n"
        f"• <b>Начало семестра:</b> {start_date.strftime('%d.%m.%Y')}\n"
        f"• <b>Сегодня:</b> {datetime.now().strftime('%d.%m.%Y')}"
    )

@dp.message(Command(commands=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]))
async def send_schedule(message: types.Message):
    """Ручная команда для получения расписания"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    init_group_data(message.chat.id)
    
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
    week_type = get_current_week(message.chat.id)
    
    text = get_schedule_for_day(message.chat.id, day_rus, week_type)
    next_week_type = "нижняя" if week_type == "верхняя" else "верхняя"
    next_week_text = get_schedule_for_day(message.chat.id, day_rus, next_week_type)
    
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
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
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

<b>⚠️ Внимание:</b> Расписание загружается только для этой группы!
    """
    
    await message.answer(help_text)

@dp.message(Command(commands=["set_schedule"]))
async def set_schedule(message: types.Message):
    """Установка расписания для конкретного дня и недели"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
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
        
        # Инициализируем данные группы если их нет
        init_group_data(message.chat.id)
        
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
            groups_data[str(message.chat.id)]["schedule"][day_rus] = schedule_text
            save_data()
            await message.answer(f"✅ Расписание для {day_rus} установлено для этой группы!")
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
        
        if day_rus not in groups_data[str(message.chat.id)]["schedule"]:
            groups_data[str(message.chat.id)]["schedule"][day_rus] = {}
        
        groups_data[str(message.chat.id)]["schedule"][day_rus][week_type_rus] = schedule_text
        save_data()
        await message.answer(f"✅ Расписание для {day_rus} ({week_type_rus} неделя) установлено для этой группы!")
        
    except Exception as e:
        logger.error(f"Ошибка установки расписания: {e}")
        await message.answer("❌ Произошла ошибка при установке расписания")

@dp.message(Command(commands=["set_start_date"]))
async def set_start_date(message: types.Message):
    """Установка даты начала семестра"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Только администраторы могут устанавливать дату начала семестра!")
        return
    
    try:
        date_str = message.text.replace("/set_start_date", "").strip()
        if not date_str:
            await message.answer("❌ Укажите дату в формате ДД.ММ.ГГГГ")
            return
        
        # Парсим дату
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        
        # Инициализируем данные группы если их нет
        init_group_data(message.chat.id)
        
        # Сохраняем дату
        groups_data[str(message.chat.id)]["start_date"] = date_obj.isoformat()
        save_data()
        
        await message.answer(f"✅ Дата начала семестра установлена: {date_str}")
        
    except ValueError:
        await message.answer("❌ Неправильный формат даты. Используйте: ДД.ММ.ГГГГ")
    except Exception as e:
        logger.error(f"Ошибка установки даты: {e}")
        await message.answer("❌ Произошла ошибка при установке даты")

@dp.message(Command(commands=["group_info"]))
async def group_info(message: types.Message):
    """Информация о группе"""
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в группах!")
        return
    
    init_group_data(message.chat.id)
    
    group_data = groups_data[str(message.chat.id)]
    start_date = datetime.fromisoformat(group_data["start_date"])
    
    info_text = (
        f"<b>📊 ИНФОРМАЦИЯ О ГРУППЕ</b>\n\n"
        f"• <b>ID группы:</b> {message.chat.id}\n"
        f"• <b>Дата создания:</b> {datetime.fromisoformat(group_data['created_at']).strftime('%d.%m.%Y %H:%M')}\n"
        f"• <b>Начало семестра:</b> {start_date.strftime('%d.%m.%Y')}\n"
        f"• <b>Текущая неделя:</b> {get_current_week(message.chat.id).capitalize()}\n"
        f"• <b>Расписание настроено:</b> {'✅' if any('❌' not in str(v) for v in group_data['schedule'].values()) else '❌'}\n\n"
        f"<i>Используйте /upload_schedule для настройки расписания</i>"
    )
    
    await message.answer(info_text)

@dp.message(Command(commands=["admins"]))
async def show_admins(message: types.Message):
    """Показать список администраторов"""
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        admins_list = "\n".join([f"• {admin_id}" for admin_id in ADMIN_IDS])
        await message.answer(f"<b>📋 Глобальные администраторы:</b>\n{admins_list}\n\n<b>Ваш ID:</b> {user_id}")
    else:
        await message.answer(f"❌ У вас нет прав для этой команды\nВаш ID: {user_id}")

async def on_startup():
    """Запуск планировщика при старте бота"""
    load_data()
    await set_bot_commands()
    
    # Расписание на 7:00 утра
    scheduler.add_job(send_daily_schedule, CronTrigger(hour=7, minute=0))
    scheduler.start()
    
    logger.info("Бот запущен и готов к работе!")
    logger.info(f"Загружены администраторы: {ADMIN_IDS}")
    logger.info(f"Загружено групп: {len(groups_data)}")

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