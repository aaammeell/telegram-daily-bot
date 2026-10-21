import asyncio
import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАСТРОЙКИ ---
BOT_TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER"
CHAT_ID = int("ВСТАВЬ_СЮДА_СВОЙ_CHAT_ID")
CITY = "Glasov"  # Укажи свой город

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ДЛЯ ДЕЛ ---
def init_db():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_task(user_id, text):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (user_id, text) VALUES (?, ?)", (user_id, text))
    conn.commit()
    conn.close()

def get_tasks(user_id):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, text FROM tasks WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def clear_tasks(user_id):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- ПОЛУЧЕНИЕ ПОДРОБНОЙ ПОГОДЫ НА ДЕНЬ ---
async def get_daily_weather_forecast(city):
    url = f"https://wttr.in/{city}?format=j1&lang=ru"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    today = data['weather'][0]
                    hourly = today['hourly']
                    
                    # Разбираем часы: 2 -> Утро (09:00), 4 -> День (15:00), 6 -> Вечер (21:00), 0 -> Ночь (03:00)
                    night = hourly[0]
                    morning = hourly[2]
                    day = hourly[4]
                    evening = hourly[6]
                    
                    def fmt(time_data):
                        temp = time_data['tempC']
                        desc = time_data['lang_ru'][0]['value'] if 'lang_ru' in time_data and time_data['lang_ru'] else time_data['weatherDesc'][0]['value']
                        sign = "+" if int(temp) > 0 else ""
                        return f"{sign}{temp}°C, {desc}"

                    report = (
                        f"🌅 **Утро:** {fmt(morning)}\n"
                        f"☀️ **День:** {fmt(day)}\n"
                        f"🌆 **Вечер:** {fmt(evening)}\n"
                        f"🌙 **Ночь:** {fmt(night)}"
                    )
                    return report
    except Exception as e:
        logging.error(f"Ошибка получения погоды: {e}")
    return "Не удалось получить прогноз погоды."

# --- УТРЕННЯЯ РАССЫЛКА ---
async def send_morning_report():
    weather_report = await get_daily_weather_forecast(CITY)
    tasks = get_tasks(CHAT_ID)
    
    if tasks:
        tasks_text = "\n".join([f"{i+1}. {t[1]}" for i, t in enumerate(tasks)])
    else:
        tasks_text = "Список дел пока пуст 🎉"

    text = (
        f"☀️ **Доброе утро! Прогноз погоды на сегодня ({CITY}):**\n\n"
        f"{weather_report}\n\n"
        f"📋 **Твои запланированные дела:**\n"
        f"{tasks_text}"
    )
    
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка отправки утреннего сообщения: {e}")

# --- КОМАНДЫ ДЛЯ ТЕЛЕГРАМ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я твой ежедневник и синоптик 🤖\n\n"
        "• Просто отправляй мне сообщением свои дела — я их запишу.\n"
        "• `/tasks` — показать список дел.\n"
        "• `/clear` — очистить список всех дел.\n"
        "• `/test` — проверить утренний отчёт прямо сейчас."
    )

@dp.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    tasks = get_tasks(message.from_user.id)
    if not tasks:
        await message.answer("У тебя пока нет сохранённых дел.")
        return
    
    text = "📋 **Твой актуальный список дел:**\n\n" + "\n".join([f"{i+1}. {t[1]}" for i, t in enumerate(tasks)])
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    clear_tasks(message.from_user.id)
    await message.answer("🧹 Все дела удалены!")

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    await send_morning_report()

# Любой входящий текст сохраняется как дело
@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"):
        return
    
    add_task(message.from_user.id, message.text)
    await message.answer(f"✅ Добавлено дело:\n> *{message.text}*", parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    init_db()
    
    # Настраиваем расписание на 06:30 утра (поставь своё время)
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_morning_report, 'cron', hour=7, minute=30)
    scheduler.start()

    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
