import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import StateFilter, ContentTypeFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import warnings

warnings.simplefilter("ignore", UserWarning)
logging.basicConfig(level=logging.INFO)

# -----------------------
# Настройки
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Или вставьте токен прямо: BOT_TOKEN = "ВАШ_ТОКЕН"
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
tournaments = {}  # {tid: {title, max_players, entry_fee, prize_places, prizes, requisites, status, participants: []}}
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
    kb.add(KeyboardButton("Уведомление оплатившим"))
    return kb

# -----------------------
# Вспомогательные функции
# -----------------------
def is_admin_func(user_id):
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
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {"username": message.from_user.username, "banned": False}
    if users[user_id]["banned"]:
        await message.answer("Вы забанены и не можете использовать бота.")
        return
    await message.answer("Добро пожаловать!", reply_markup=main_menu(is_admin_func(user_id)))

# -----------------------
# Админ панель кнопки
# -----------------------
@dp.message(lambda m: m.text == "Админ панель" and is_admin_func(m.from_user.id))
async def admin_panel(message: types.Message):
    await message.answer("Админ панель:", reply_markup=admin_panel_buttons())

# -----------------------
# Просмотр турниров
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
    if not t:
        await call.answer("Турнир не найден.", show_alert=True)
        return
    if len(t["participants"]) >= t["max_players"]:
        await call.answer("Мест нет!", show_alert=True)
        return
    if get_participant(t, call.from_user.id):
        await call.answer("Вы уже зарегистрированы!", show_alert=True)
        return
    await state.set_state(Registration.nickname)
    await state.update_data(tournament_id=tid)
    await call.message.answer("Введите ваш ник для турнира:")
    await call.answer()

@dp.message(Registration.nickname)
async def set_nickname(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['tournament_id']
    t = tournaments[tid]
    t["participants"].append({
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "nickname": message.text,
        "paid": False,
        "payment_screenshot": None,
        "finished": False,
        "place": None,
        "result_screenshot": None,
        "requisites": None
    })
    await message.answer(f"Вы зарегистрированы на турнир '{t['title']}'.\nОтправьте скрин оплаты:")
    await state.set_state(Registration.payment_screenshot)

@dp.message(Registration.payment_screenshot, StateFilter(Registration.payment_screenshot), ContentTypeFilter(types.ContentType.PHOTO))
async def payment_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['tournament_id']
    t = tournaments[tid]
    p = get_participant(t, message.from_user.id)
    if not p:
        await message.answer("Ошибка регистрации")
        await state.clear()
        return
    p["payment_screenshot"] = message.photo[-1].file_id
    p["paid"] = True
    await message.answer("Скрин оплаты отправлен администратору. Ожидайте подтверждения.")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, p["payment_screenshot"],
                                 caption=f"Новая оплата от {p['nickname']} для турнира '{t['title']}'. Подтвердите через меню.")
        except: pass
    await state.clear()

# -----------------------
# Админ: Создание турнира
# -----------------------
@dp.message(lambda m: m.text == "Создать турнир" and is_admin_func(m.from_user.id))
async def admin_create_start(message: types.Message, state: FSMContext):
    await state.set_state(AdminCreateTournament.title)
    await message.answer("Введите название турнира:")

@dp.message(AdminCreateTournament.title)
async def admin_create_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminCreateTournament.max_players)
    await message.answer("Введите максимальное количество участников:")

@dp.message(AdminCreateTournament.max_players)
async def admin_create_max_players(message: types.Message, state: FSMContext):
    try:
        await state.update_data(max_players=int(message.text))
    except ValueError:
        await message.answer("Введите число!")
        return
    await state.set_state(AdminCreateTournament.entry_fee)
    await message.answer("Введите цену входа (₽):")

@dp.message(AdminCreateTournament.entry_fee)
async def admin_create_entry_fee(message: types.Message, state: FSMContext):
    try:
        await state.update_data(entry_fee=int(message.text))
    except ValueError:
        await message.answer("Введите число!")
        return
    await state.set_state(AdminCreateTournament.prize_places)
    await message.answer("Введите количество призовых мест:")

@dp.message(AdminCreateTournament.prize_places)
async def admin_create_prize_places(message: types.Message, state: FSMContext):
    try:
        await state.update_data(prize_places=int(message.text))
    except ValueError:
        await message.answer("Введите число!")
        return
    await state.set_state(AdminCreateTournament.prizes)
    await message.answer("Введите призы через запятую (например: 500, 300, 200):")

@dp.message(AdminCreateTournament.prizes)
async def admin_create_prizes(message: types.Message, state: FSMContext):
    await state.update_data(prizes=[p.strip() for p in message.text.split(",")])
    await state.set_state(AdminCreateTournament.requisites)
    await message.answer("Введите реквизиты для оплаты (или оставьте пустым для дефолтных):")

@dp.message(AdminCreateTournament.requisites)
async def admin_create_requisites(message: types.Message, state: FSMContext):
    global next_tid
    data = await state.get_data()
    tournaments[next_tid] = {
        "title": data['title'],
        "max_players": data['max_players'],
        "entry_fee": data['entry_fee'],
        "prize_places": data['prize_places'],
        "prizes": data['prizes'],
        "requisites": message.text if message.text.strip() else DEFAULT_REQUISITES,
        "status": "active",
        "participants": []
    }
    await message.answer(f"Турнир '{data['title']}' создан с ID {next_tid}")
    next_tid += 1
    await state.clear()

# -----------------------
# Админ: Завершение турнира
# -----------------------
@dp.message(lambda m: m.text == "Завершить турнир" and is_admin_func(m.from_user.id))
async def admin_finish_tournament(message: types.Message, state: FSMContext):
    active = get_active_tournaments()
    if not active:
        await message.answer("Нет активных турниров для завершения")
        return
    kb = InlineKeyboardMarkup()
    for tid, title in active:
        kb.add(InlineKeyboardButton(title, callback_data=f"finish_{tid}"))
    await message.answer("Выберите турнир для завершения:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("finish_"))
async def finish_tournament(call: types.CallbackQuery):
    tid = int(call.data.split("_")[1])
    t = tournaments.get(tid)
    if not t:
        await call.answer("Турнир не найден", show_alert=True)
        return
    t["status"] = "finished"
    # уведомляем участников
    for p in t["participants"]:
        if p["paid"]:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Выиграл", callback_data=f"won_{tid}_{p['user_id']}"))
            kb.add(InlineKeyboardButton("Проиграл", callback_data=f"lost_{tid}_{p['user_id']}"))
            try:
                await bot.send_message(p["user_id"], f"Турнир '{t['title']}' завершен! Выберите результат:", reply_markup=kb)
            except: pass
    await call.message.answer(f"Турнир '{t['title']}' завершен и участники уведомлены.")
    await call.answer()

# -----------------------
# Участники: Выиграл / Проиграл
# -----------------------
@dp.callback_query(lambda c: c.data.startswith("won_") or c.data.startswith("lost_"))
async def result_selection(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    action = parts[0]
    tid = int(parts[1])
    user_id = int(parts[2])
    t = tournaments.get(tid)
    if not t:
        await call.answer("Турнир не найден", show_alert=True)
        return
    p = get_participant(t, user_id)
    if not p:
        await call.answer("Вы не участвуете", show_alert=True)
        return
    if action == "won":
        await state.set_state(ResultSubmission.screenshot)
        await state.update_data(tournament_id=tid)
        await call.message.answer("Вы выбрали 'Выиграл'. Отправьте скрин результата:")
    else:
        p["finished"] = True
        p["place"] = None
        await call.message.answer("Вы выбрали 'Проиграл'. Спасибо за участие!")
    await call.answer()

@dp.message(ResultSubmission.screenshot, StateFilter(ResultSubmission.screenshot), ContentTypeFilter(types.ContentType.PHOTO))
async def result_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['tournament_id']
    t = tournaments.get(tid)
    p = get_participant(t, message.from_user.id)
    if not p:
        await message.answer("Ошибка")
        await state.clear()
        return
    p["result_screenshot"] = message.photo[-1].file_id
    await message.answer("Отправьте ваши реквизиты для выплаты:")
    await state.set_state(ResultSubmission.requisites)

@dp.message(ResultSubmission.requisites, StateFilter(ResultSubmission.requisites))
async def result_requisites(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tid = data['tournament_id']
    t = tournaments.get(tid)
    p = get_participant(t, message.from_user.id)
    if not p:
        await message.answer("Ошибка")
        await state.clear()
        return
    p["requisites"] = message.text
    p["finished"] = True
    await message.answer("Спасибо! Ваш результат и реквизиты сохранены.")
    # уведомление админа
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"Участник {p['nickname']} выиграл турнир '{t['title']}'. Реквизиты: {p['requisites']}")
            await bot.send_photo(admin_id, p["result_screenshot"], caption=f"Скрин результата {p['nickname']}")
        except: pass
    await state.clear()

# -----------------------
# Запуск бота
# -----------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
