import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pymongo
from prettytable import PrettyTable
import schedule
import time
import datetime
import os
import logging

# Log dosyasının bulunduğu klasörü kontrol et ve gerekirse oluştur
log_directory = "/bot/logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Loglama yapılandırması
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s',
                    handlers=[logging.FileHandler(f"{log_directory}/mail_schedule.log"),
                              logging.StreamHandler()])

# Veritabanı bağlantısı
client = pymongo.MongoClient("mongodb://mongo:27017")
db = client["trading"]
collection = db["signals"]

# E-posta bilgileri
sender_email = os.environ.get("EMAIL_USER", "test@test.com")
receiver_email = os.environ.get("EMAIL_RECEIVER", "test@test.com")
password = os.environ.get("EMAIL_PASSWORD", "password")
smtp_host= os.environ.get("EMAIL_SMTP", "smtp.test.com")
smtp_port = os.environ.get("EMAIL_PORT", 465)

def format_trade_data_to_html(trades, fields):
    table = PrettyTable()
    table.field_names = fields
    for trade in trades:
        row = [trade.get(field, "") for field in fields]
        table.add_row(row)
    return table.get_html_string()

def send_email(subject, html_content):
    message = MIMEMultipart("alternative")
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    # HTML içeriğini ekle
    message.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        logging.info("Email sent successfully.")
    except Exception as e:
        logging.error(f"Error sending email: {e}")

def fetch_and_send_trades():
    logging.info(f"Fetching and sending trades... datetime: {datetime.datetime.now()}")
    now = datetime.datetime.now()
    one_hour_ago = now - datetime.timedelta(hours=1)
    twenty_four_hours_ago = now - datetime.timedelta(hours=24)

    # Veri çekme sorguları ve alanlar
    new_purchases = collection.find({"status": 2, "entry_time": {"$gte": one_hour_ago}})
    recent_sales = collection.find({"status": 4, "exit_time": {"$gte": one_hour_ago}})
    last_day_sales = collection.find({"status": 4, "exit_time": {"$gte": twenty_four_hours_ago}})
    open_trades = collection.find({"status": {"$lt": 4}})

    purchase_fields = [
        "symbol",         # Coin
        "entry_price",    # Purchase Price
        "entry_amount",   # Quantity
        "entry_amount_usdt", # USDT Amount
        "entry_rsi"       # RSI
    ]

    sale_fields = [
        "symbol",            # Coin
        "entry_price",       # Purchase Price
        "entry_amount",      # Quantity
        "entry_amount_usdt", # USDT Amount
        "entry_rsi",         # Purchase RSI
        "exit_price",        # Sale Price
        "exit_rsi",          # Sale RSI
        "profit_percentage", # Profit %
        "profit"             # Profit USDT
    ]

    open_trade_fields = [
        "symbol",         # Coin
        "status",         # Status
        "entry_price",    # Entry Price
        "entry_amount",   # Quantity
        "entry_amount_usdt" # USDT Amount
    ]


    # Rapor formatlama ve e-posta gönderimi
    html_body = "<h1>Hourly Trade Update</h1>"
    html_body += "<h2>New Purchases:</h2>" + format_trade_data_to_html(new_purchases, purchase_fields)
    html_body += "<h2>Recent Sales:</h2>" + format_trade_data_to_html(recent_sales, sale_fields)
    html_body += "<h2>Last Day Sales:</h2>" + format_trade_data_to_html(last_day_sales, sale_fields)
    html_body += "<h2>Open Trades:</h2>" + format_trade_data_to_html(open_trades, open_trade_fields)

    

    try:
        send_email("Hourly Trade Update", html_body)
    except Exception as e:
        logging.error(f"Error sending email: {e}")

# Zamanlama
schedule.every().hour.at(":01").do(fetch_and_send_trades)

# İlk çalıştırmayı başlat
logging.info("Starting first run...")
fetch_and_send_trades()

# Döngüyü başlat
while True:
    schedule.run_pending()
    time.sleep(1)
