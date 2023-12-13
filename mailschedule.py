import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pymongo
from prettytable import PrettyTable
import schedule
import time
import datetime
import os

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

print(f"Password: {password}")
def format_trade_data(trades, fields):
    table = PrettyTable()
    table.field_names = fields
    for trade in trades:
        row = [trade.get(field, "") for field in fields]
        table.add_row(row)
    return table.get_string()

def send_email(subject, body):
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())

def fetch_and_send_trades():
    print(f"Fetching and sending trades... time: {datetime.datetime.now()}")
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


    # Rapor formatlama
    body = "New Purchases:\n" + format_trade_data(new_purchases, purchase_fields)
    body += "\n\nRecent Sales:\n" + format_trade_data(recent_sales, sale_fields)
    body += "\n\nLast Day Sales:\n" + format_trade_data(last_day_sales, sale_fields)
    body += "\n\nOpen Trades:\n" + format_trade_data(open_trades, open_trade_fields)

    try:
        send_email("Hourly Trade Update", body)
    except Exception as e:
        print(f"Error sending email: {e}")

# Zamanlama
schedule.every().hour.at(":10").do(fetch_and_send_trades)

fetch_and_send_trades()
while True:
    schedule.run_pending()
    time.sleep(1)
