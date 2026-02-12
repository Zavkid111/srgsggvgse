import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import warnings

# -----------------------
# Подавление варнингов Pydantic
# -----------------------
warnings.simplefilter("ignore", UserWarning)

# -----------------------
# Настройки
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # токен от BotHost
ADMIN_IDS = [8549130203]           # твой ID
DEFAULT_REQUISITES = "Сбербанк\n2202208214031917\nЗавкиддин А."

logging.basicConfig(level=logging.INFO)

# -----------------------
# FSM состояния
# -----------------------
class CreateTournament(StatesGroup):
    title = State()
    max_players = State()
    entry_fee = State()
    prize_places = State()
    prizes = State()

class Registration(StatesGroup):
    nickname = State()

class ResultSubmission(StatesGroup):
    place = State()
    requisites = State()

# -----------------------
# Хранилища в памяти
# -----------------------
users = {}          # {user_id: username}
tournaments = {}    # {tid: {title, max_players, entry_fee, prize_places, prizes, status, participants:[]}}
next_tid = 1

# -----------------------
# Вспомогательные функции
# -----------------------
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_active_tournaments():
    return [(tid, t["title"]) for tid, t in tournaments.items() if t["status"] == "active"]

# -----------------------
# Инициализация бота
# -----------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -----------------------
# Стартовые команды
# -----------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    users[message.from_user.id] = message.from_user.username
    await message.answer(
        "Добро пожаловать в турнирный бот!\n"
        "Используй /tournaments чтобы посмотреть текущие турниры"
    )

# -----------------------
# Админ-панель
# -----------------------
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Админ панель:\n"
        "/create - создать турнир\n"
        "/finish <id> - завершить турнир\n"
        "/result <id> - собрать результаты\n"
        "/notify <сообщение> - уведомить всех участников"
    )

# -----------------------
# Создание турнира
# -----------------------
@dp.message(Command("create"))
async def create_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(CreateTournament.title)
    await message.answer("Введите название турнира:")

@dp.message(CreateTournament.title)
async def create_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(CreateTournament.max_players)
    await message.answer("Количество мест:")

@dp.message(CreateTournament.max_players)
async def create_max_players(message: types.Message, state: FSMContext):
    await state.update_data(max_players=int(message.text))
    await state.set_state(CreateTournament.entry_fee)
    await message.answer("Стоимость участия (0 если бесплатно):")

@dp.message(CreateTournament.entry_fee)
async def create_entry_fee(message: types.Message, state: FSMContext):
    await state.update_data(entry_fee=int(message.text))
    await state.set_state(CreateTournament.prize_places)
    await message.answer("Количество призовых мест:")

@dp.message(CreateTournament.prize_places)
async def create_prize_places(message: types.Message, state: FSMContext):
    await state.update_data(prize_places=int(message.text))
    await state.set_state(CreateTournament.prizes)
    await message.answer("Опиши призы через запятую:")

@dp.message(CreateTournament.prizes)
async def create_prizes(message: types.Message, state: FSMContext):
    global next_tid
    data = await state.get_data()
    tournaments[next_tid] = {
        "title": data['title'],
        "max_players": data['max_players'],
        "entry_fee": data['entry_fee'],
        "prize_places": data['prize_places'],
        "prizes": message.text,
        "status": "active",
        "participants": []
    }
    await message.answer(f"Турнир '{data['title']}' создан с ID {next_tid}!")
    next_tid += 1
    await state.clear()

# -----------------------
# Завершение турнира
# -----------------------
@dp.message(Command("finish"))
async def finish_tournament(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        tid = int(message.text.split()[1])
    except:
        await message.answer("Использование: /finish <id>")
        return
    if tid in tournaments:
        tournaments[tid]["status"] = "finished"
        await message.answer(f"Турнир {tid} завершен!")

# -----------------------
# Уведомления всем участникам
# -----------------------
@dp.message(Command("notify"))
async def notify_all(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.partition(" ")[2]
    if not text:
        await message.answer("Использование: /notify <текст>")
        return
    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 Уведомление от админа:\n{text}")
        except:
            continue
    await message.answer("Уведомления отправлены всем участникам.")

# -----------------------
# Просмотр турниров и регистрация
# -----------------------
@dp.message(Command("tournaments"))
async def list_tournaments(message: types.Message):
    active = get_active_tournaments()
    if not active:
        await message.answer("Нет активных турниров")
        return
    kb = InlineKeyboardMarkup()
    for tid, title in active:
        kb.add(InlineKeyboardButton(title, callback_data=f"join_{tid}"))
    await message.answer("Выберите турнир:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("join_"))
async def join_tournament(call: types.CallbackQuery, state: FSMContext):
    tid = int(call.data.split("_")[1])
    await state.set_state(Registration.nickname)
    await state.update_data(tournament_id=tid)
    await call.message.answer("Введите свой ник:")
    await call.answer()

@dp.message(Registration.nickname)
async def set_nickname(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['tournament_id']
    t = tournaments[tid]
    for p in t["participants"]:
        if p["user_id"] == message.from_user.id:
            await message.answer("Вы уже зарегистрированы!")
            await state.clear()
            return
    t["participants"].append({
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "nickname": message.text,
        "place": None,
        "requisites": None
    })
    await message.answer("Вы зарегистрированы!")
    await state.clear()

# -----------------------
# FSM для результатов
# -----------------------
@dp.message(Command("result"))
async def start_result(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        tid = int(message.text.split()[1])
    except:
        await message.answer("Использование: /result <id>")
        return
    await state.set_state(ResultSubmission.place)
    await state.update_data(tournament_id=tid)
    await message.answer("Начинаем сбор результатов. Введите место участника:")

@dp.message(ResultSubmission.place)
async def result_place(message: types.Message, state: FSMContext):
    try:
        place = int(message.text)
    except:
        await message.answer("Введите число для места!")
        return
    await state.update_data(place=place)
    await state.set_state(ResultSubmission.requisites)
    await message.answer("Введите реквизиты для выплаты (или 'по умолчанию'):")

@dp.message(ResultSubmission.requisites)
async def result_requisites(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['tournament_id']
    place = data['place']
    requisites = DEFAULT_REQUISITES if message.text.lower() == "по умолчанию" else message.text

    # Найдем первого участника без места
    t = tournaments[tid]
    for p in t["participants"]:
        if p["place"] is None:
            p["place"] = place
            p["requisites"] = requisites
            # уведомление игроку
            try:
                asyncio.create_task(bot.send_message(p["user_id"],
                    f"🏆 Вы заняли {place} место в турнире '{t['title']}'!\nРеквизиты для выплаты:\n{requisites}"))
            except:
                pass
            break

    await message.answer(f"Результат для места {place} сохранен.")
    await state.set_state(ResultSubmission.place)
    await message.answer("Введите следующий результат или /finish для завершения сбора.")

# -----------------------
# Запуск бота
# -----------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

