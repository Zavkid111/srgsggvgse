import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# -----------------------
# Настройки
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # или вставьте токен прямо
ADMIN_IDS = [8549130203]
DEFAULT_REQUISITES = "Сбербанк\n2202208214031917\nЗавкиддин А."

# -----------------------
# FSM состояния
# -----------------------
class Registration(StatesGroup):
    nickname = State()
    payment_screenshot = State()

class ResultSubmission(StatesGroup):
    screenshot = State()
    requisites = State()

class AdminCreateTournament(StatesGroup):
    title = State()
    max_players = State()
    entry_fee = State()
    prize_places = State()
    prizes = State()
    requisites = State()

# -----------------------
# Хранилища
# -----------------------
users = {}  # {user_id: {"username": str, "banned": bool}}
tournaments = {}  # {tid: {title, max_players, entry_fee, prize_places, prizes, requisites, status, participants}}
next_tid = 1

# -----------------------
# Инициализация бота
# -----------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -----------------------
# Кнопки
# -----------------------
def main_menu(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Турниры"))
    if is_admin:
        kb.add(KeyboardButton("Админ панель"))
    return kb

def admin_panel_buttons():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Создать турнир"))
    kb.add(KeyboardButton("Завершить турнир"))
    kb.add(KeyboardButton("Подтвердить оплату"))
    kb.add(KeyboardButton("Бан/Разбан"))
    kb.add(KeyboardButton("Уведомление всем"))
    return kb

# -----------------------
# Вспомогательные функции
# -----------------------
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_active_tournaments():
    return [(tid, t["title"]) for tid, t in tournaments.items() if t["status"] == "active"]

def get_participant(tournament, user_id):
    for p in tournament["participants"]:
        if p["user_id"] == user_id:
            return p
    return None

# -----------------------
# Старт
# -----------------------
@dp.message(lambda m: m.text.lower() in ["/start", "старт", "start"])
async def start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in users:
        users[uid] = {"username": message.from_user.username, "banned": False}
    if users[uid]["banned"]:
        await message.answer("Вы забанены!")
        return
    await message.answer("Добро пожаловать!", reply_markup=main_menu(is_admin(uid)))

# -----------------------
# Админ панель
# -----------------------
@dp.message(lambda m: m.text == "Админ панель" and is_admin(m.from_user.id))
async def admin_panel(message: types.Message):
    await message.answer("Админ панель:", reply_markup=admin_panel_buttons())

# -----------------------
# Турниры
# -----------------------
@dp.message(lambda m: m.text == "Турниры")
async def show_tournaments(message: types.Message, state: FSMContext):
    active = get_active_tournaments()
    if not active:
        await message.answer("Нет активных турниров.")
        return
    kb = InlineKeyboardMarkup()
    for tid, title in active:
        kb.add(InlineKeyboardButton(title, callback_data=f"join_{tid}"))
    await message.answer("Выберите турнир:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("join_"))
async def join_tournament(call: types.CallbackQuery, state: FSMContext):
    tid = int(call.data.split("_")[1])
    t = tournaments.get(tid)
    if not t or len(t["participants"]) >= t["max_players"]:
        await call.answer("Невозможно присоединиться!", show_alert=True)
        return
    if get_participant(t, call.from_user.id):
        await call.answer("Вы уже зарегистрированы!", show_alert=True)
        return
    await state.set_state(Registration.nickname)
    await state.update_data(tournament_id=tid)
    await call.message.answer("Введите ваш ник:")
    await call.answer()

@dp.message(Registration.nickname)
async def set_nickname(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data["tournament_id"]
    t = tournaments[tid]
    t["participants"].append({
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "nickname": message.text,
        "paid": False,
        "payment_screenshot": None,
        "finished": False,
        "requisites": None
    })
    await message.answer(f"Вы зарегистрированы на турнир '{t['title']}'. Отправьте скрин оплаты:")
    await state.set_state(Registration.payment_screenshot)

@dp.message(Registration.payment_screenshot)
async def payment_screenshot(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Отправьте именно фото!")
        return
    data = await state.get_data()
    tid = data["tournament_id"]
    t = tournaments[tid]
    p = get_participant(t, message.from_user.id)
    p["payment_screenshot"] = message.photo[-1].file_id
    p["paid"] = True
    await message.answer("Скрин отправлен администратору.")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, p["payment_screenshot"], caption=f"Новая оплата: {p['nickname']} для '{t['title']}'")
        except: pass
    await state.clear()

# -----------------------
# Админ: Создание турнира
# -----------------------
@dp.message(lambda m: m.text == "Создать турнир" and is_admin(m.from_user.id))
async def create_tournament(message: types.Message, state: FSMContext):
    await state.set_state(AdminCreateTournament.title)
    await message.answer("Введите название турнира:")

@dp.message(AdminCreateTournament.title)
async def create_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminCreateTournament.max_players)
    await message.answer("Введите максимальное количество участников:")

@dp.message(AdminCreateTournament.max_players)
async def create_max(message: types.Message, state: FSMContext):
    await state.update_data(max_players=int(message.text))
    await state.set_state(AdminCreateTournament.entry_fee)
    await message.answer("Введите цену входа:")

@dp.message(AdminCreateTournament.entry_fee)
async def create_fee(message: types.Message, state: FSMContext):
    await state.update_data(entry_fee=int(message.text))
    await state.set_state(AdminCreateTournament.prize_places)
    await message.answer("Введите количество призовых мест:")

@dp.message(AdminCreateTournament.prize_places)
async def create_places(message: types.Message, state: FSMContext):
    await state.update_data(prize_places=int(message.text))
    await state.set_state(AdminCreateTournament.prizes)
    await message.answer("Введите призы через запятую:")

@dp.message(AdminCreateTournament.prizes)
async def create_prizes(message: types.Message, state: FSMContext):
    await state.update_data(prizes=[p.strip() for p in message.text.split(",")])
    await state.set_state(AdminCreateTournament.requisites)
    await message.answer("Введите реквизиты (или пусто для дефолтных):")

@dp.message(AdminCreateTournament.requisites)
async def create_requisites(message: types.Message, state: FSMContext):
    global next_tid
    data = await state.get_data()
    tournaments[next_tid] = {
        "title": data["title"],
        "max_players": data["max_players"],
        "entry_fee": data["entry_fee"],
        "prize_places": data["prize_places"],
        "prizes": data["prizes"],
        "requisites": message.text if message.text.strip() else DEFAULT_REQUISITES,
        "status": "active",
        "participants": []
    }
    await message.answer(f"Турнир '{data['title']}' создан!")
    next_tid += 1
    await state.clear()

# -----------------------
# Запуск
# -----------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
