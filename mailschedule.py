import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pymongo
import schedule
import time
import datetime
import os

# Veritabanı bağlantısı
client = pymongo.MongoClient("mongodb://mongo:27017")
db = client["trading"]
collection = db["signals"]

# E-posta bilgileri
sender_email = "autobot@nvrbox.com"
receiver_email = "cervantes79@gmail.com"
password = os.environ.get("EMAIL_PASSWORD", "password")

def send_email(subject, body):
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("mail.nvrbox.com", 465) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())

def fetch_and_send_trades():
    now = datetime.datetime.now()
    one_hour_ago = now - datetime.timedelta(hours=1)

    open_trades = collection.find({"status": {"$lt": 4}, "entry_time": {"$gte": one_hour_ago}})
    closed_trades = collection.find({"status": 4, "entry_time": {"$gte": one_hour_ago}})

    body = "Open Trades:\n" + "\n".join([str(trade) for trade in open_trades])
    body += "\n\nClosed Trades:\n"
    body += "\n".join([str(trade) for trade in closed_trades])

    send_email("Hourly Trade Update", body)

# Schedule to run every hour
schedule.every().hour.do(fetch_and_send_trades)

while True:
    schedule.run_pending()
    time.sleep(1)
