import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = "8532407173:AAH0JKkebenb_N5iOva2Njb7ubUhkwvzc38"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('werx_bot.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 1000,
    daily_streak INTEGER DEFAULT 0,
    last_daily TEXT,
    games_played INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS bets_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, game TEXT, bet INTEGER, result TEXT, change INTEGER, time TEXT
)''')
conn.commit()

def get_user(user_id):
    c.execute('SELECT balance, daily_streak, last_daily, games_played, games_won FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if not row:
        c.execute('INSERT INTO users (user_id, balance) VALUES (?,?)', (user_id, 1000))
        conn.commit()
        return 1000, 0, None, 0, 0
    return row

def update_user(user_id, balance_delta=0, games_played_inc=0, games_won_inc=0):
    if balance_delta != 0:
        c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (balance_delta, user_id))
    if games_played_inc:
        c.execute('UPDATE users SET games_played = games_played + ? WHERE user_id = ?', (games_played_inc, user_id))
    if games_won_inc:
        c.execute('UPDATE users SET games_won = games_won + ? WHERE user_id = ?', (games_won_inc, user_id))
    conn.commit()

def log_bet(user_id, game, bet, result, change):
    c.execute('INSERT INTO bets_log (user_id, game, bet, result, change, time) VALUES (?,?,?,?,?,?)',
              (user_id, game, bet, result, change, datetime.now().isoformat()))
    conn.commit()

# --- ЕЖЕДНЕВНЫЙ БОНУС ---
@dp.message(Command("daily"))
async def daily_bonus(message: types.Message):
    user_id = message.from_user.id
    balance, streak, last_daily, _, _ = get_user(user_id)
    
    today = datetime.now().date()
    last_date = datetime.fromisoformat(last_daily).date() if last_daily else None
    
    if last_date == today:
        await message.answer("Ты уже получил бонус сегодня!")
        return
    
    if last_date and last_date == today - timedelta(days=1):
        streak += 1
    else:
        streak = 1
    
    bonus = min(100 + (streak - 1) * 20, 500)
    update_user(user_id, balance_delta=bonus)
    c.execute('UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?', (streak, datetime.now().isoformat(), user_id))
    conn.commit()
    
    await message.answer(f"Ежедневный бонус! Стрейк: {streak} дней\nПолучено: {bonus} Werx\nБаланс: {balance + bonus} Werx")

# --- ИГРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    balance, _, _, _, _ = get_user(user_id)
    await message.answer(
        f"Добро пожаловать в Werx Casino!\nБаланс: {balance} Werx\n\n"
        f"Игры:\n🎲 кубы <ставка> <число 1-6> (x2)\n"
        f"🎰 казино <ставка> <чет/нечет/красное/черное> (x2)\n"
        f"💣 mines <ставка> (x3)\n"
        f"🎰 слоты <ставка>\n\n"
        f"Команды:\n/balance - баланс\n/daily - бонус дня\n/top - топ игроков\n/history - история ставок"
    )

@dp.message(Command("balance"))
async def show_balance(message: types.Message):
    balance, _, _, _, _ = get_user(message.from_user.id)
    await message.answer(f"Баланс: {balance} Werx")

@dp.message(Command("top"))
async def show_top(message: types.Message):
    c.execute('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10')
    top = c.fetchall()
    text = "Топ-10 игроков по балансу:\n\n"
    for i, (uid, bal) in enumerate(top, 1):
        text += f"{i}. ID{uid} — {bal} Werx\n"
    await message.answer(text)

@dp.message(Command("history"))
async def show_history(message: types.Message):
    c.execute('SELECT game, bet, result, change, time FROM bets_log WHERE user_id = ? ORDER BY id DESC LIMIT 10', (message.from_user.id,))
    rows = c.fetchall()
    if not rows:
        await message.answer("История пуста")
        return
    text = "Последние 10 ставок:\n\n"
    for game, bet, result, change, tm in rows:
        sign = "+" if change > 0 else ""
        text += f"{tm[5:16]} {game} {bet} | {sign}{change}\n"
    await message.answer(text)

@dp.message()
async def handle_games(message: types.Message):
    user_id = message.from_user.id
    text = message.text.lower().strip()
    balance, _, _, _, _ = get_user(user_id)

    # --- КУБЫ ---
    if text.startswith("кубы "):
        parts = text.split()
        if len(parts) != 3:
            await message.answer("Формат: кубы 100 4")
            return
        try:
            bet = int(parts[1])
            guess = int(parts[2])
            if bet < 10 or bet > balance or guess < 1 or guess > 6:
                await message.answer(f"Ставка от 10 до {balance}, число от 1 до 6")
                return
        except:
            await message.answer("Ошибка ввода")
            return
        
        roll = random.randint(1, 6)
        win = (roll == guess)
        delta = bet if win else -bet
        update_user(user_id, balance_delta=delta, games_played_inc=1, games_won_inc=1 if win else 0)
        log_bet(user_id, "dice", bet, f"guess={guess},roll={roll}", delta)
        
        await message.answer(f"🎲 Выпало: {roll}\n{'✅ +' + str(bet) if win else '❌ -' + str(bet)}\nБаланс: {balance + delta} Werx")

    # --- КАЗИНО ---
    elif text.startswith("казино "):
        parts = text.split()
        if len(parts) != 3:
            await message.answer("Формат: казино 100 чет")
            return
        try:
            bet = int(parts[1])
            bet_type = parts[2]
            if bet < 10 or bet > balance or bet_type not in ("чет","нечет","красное","черное"):
                await message.answer(f"Ставка от 10 до {balance}, тип: чет/нечет/красное/черное")
                return
        except:
            await message.answer("Ошибка ввода")
            return
        
        num = random.randint(7, 14)
        is_even = num % 2 == 0
        is_red = num in (7,9,12,14)
        color = "красное" if is_red else "черное"
        
        win = (bet_type == "чет" and is_even) or (bet_type == "нечет" and not is_even) or \
              (bet_type == "красное" and is_red) or (bet_type == "черное" and not is_red)
        delta = bet if win else -bet
        update_user(user_id, balance_delta=delta, games_played_inc=1, games_won_inc=1 if win else 0)
        log_bet(user_id, "casino", bet, f"num={num},type={bet_type}", delta)
        
        await message.answer(f"🎲 Выпало: {num} ({color}, {'чет' if is_even else 'нечет'})\n{'✅ +' + str(bet) if win else '❌ -' + str(bet)}\nБаланс: {balance + delta} Werx")

    # --- MINES ---
    elif text.startswith("mines "):
        parts = text.split()
        if len(parts) != 2:
            await message.answer("Формат: mines 100")
            return
        try:
            bet = int(parts[1])
            if bet < 10 or bet > balance:
                await message.answer(f"Ставка от 10 до {balance}")
                return
        except:
            await message.answer("Ошибка ввода")
            return
        
        field = [0]*25
        for pos in random.sample(range(25), 5):
            field[pos] = 1
        
        picks = random.sample(range(25), 3)
        hit_mine = any(field[p] == 1 for p in picks)
        
        if hit_mine:
            delta = -bet
            result_text = "💣 МИНА! Проигрыш"
        else:
            delta = bet * 3
            result_text = "💎 3 алмаза! Выигрыш x3"
        
        update_user(user_id, balance_delta=delta, games_played_inc=1, games_won_inc=1 if not hit_mine else 0)
        log_bet(user_id, "mines", bet, f"hit_mine={hit_mine}", delta)
        await message.answer(f"{result_text}\n💰 Баланс: {balance + delta} Werx")

    # --- СЛОТЫ ---
    elif text.startswith("слоты "):
        parts = text.split()
        if len(parts) != 2:
            await message.answer("Формат: слоты 100")
            return
        try:
            bet = int(parts[1])
            if bet < 10 or bet > balance:
                await message.answer(f"Ставка от 10 до {balance}")
                return
        except:
            await message.answer("Ошибка ввода")
            return
        
        reel = ["🍒", "🍒", "🔔", "🔔", "7", "🍒", "🔔", "🍒", "7", "🍒"]
        result = [random.choice(reel) for _ in range(3)]
        
        if result[0] == result[1] == result[2] == "7":
            delta = bet * 10
            msg = "ДЖЕКПОТ! x10"
        elif result[0] == result[1] == result[2] == "🔔":
            delta = bet * 3
            msg = "ТРИ КОЛОКОЛЬЧИКА! x3"
        elif result[0] == result[1] == result[2] == "🍒":
            delta = bet * 2
            msg = "ТРИ ВИШНИ! x2"
        else:
            delta = -bet
            msg = "ПРОИГРЫШ"
        
        update_user(user_id, balance_delta=delta, games_played_inc=1, games_won_inc=1 if delta > 0 else 0)
        log_bet(user_id, "slots", bet, f"{result}", delta)
        await message.answer(f"🎰 {' | '.join(result)}\n{msg}\n💰 Баланс: {balance + delta} Werx")

async def main():
    print("Бот Werx запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())