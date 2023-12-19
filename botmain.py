import contextlib
import ccxt
from pymongo import MongoClient
from datetime import datetime, timedelta
import yaml
import time
from threading import Thread
from multiprocessing import Pool, cpu_count
import pandas as pd
import pandas_ta as ta
import os
import logging
import sys
import traceback

log_directory = "/bot/logs"
log_filename = "autobot.log"

# Eğer log klasörü mevcut değilse oluştur
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Tam log dosyası yolu
log_file_path = os.path.join(log_directory, log_filename)

# Logger'ı yapılandır
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Dosya Handler'ı oluştur
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(message)s')
file_handler.setFormatter(file_format)

# Ekran (Konsol) Handler'ı oluştur
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_format = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(message)s')
stream_handler.setFormatter(stream_format)

# Handler'ları logger'a ekle
logger.addHandler(file_handler)
logger.addHandler(stream_handler)




exchange= None
config=None
ccxt_info=None
trade_parameters=None
settings=None
timeframe=None
collection = None

def fetch_rsi(symbol='BTC/USDT', timeframe='15m', limit=500, rsi_length=14, item=1):
    search_item = item * (-1)
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if len(ohlcv):
            df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df['RSI'] = ta.rsi(df['close'], length=rsi_length)
            # logger.info(f"RSI calculated for {symbol}")
            return df['RSI'].iloc[search_item]
    except Exception as e:
        logger.error(f"Error in fetch_rsi for {symbol}: {e} - {traceback.format_exc()}")
        return None


def get_ticker_list(tickers):
    global trade_parameters
    rejected_list=trade_parameters["rejected_list"]
    thick_list=[]
    for symbol, ticker in tickers.items():
        if ticker['bid'] is None or ticker['ask'] is None:
            continue
        
        if symbol.endswith('/USDT') is False:
            continue
        for i in rejected_list:
            if i in symbol:
                continue
        if "UP/" in symbol or "DOWN/" in symbol:
            continue

        stg = {
            'symbol': symbol,
            'bid': float(ticker['bid']),
            'ask': float(ticker['ask']),
            'volume': float(ticker['info']['volume'])
        }
        thick_list.append(stg)
    return thick_list

def get_ticker_info():
    global exchange

    try:
        logger.info(f"Fetching tickers... {exchange.name}")
        if 'fetchTickers' not in exchange.has:
            logger.warning('Exchange does not have the endpoint to fetch all tickers from the API.')
            return []
        tickers = exchange.fetch_tickers()
        # logger.info("Tickers fetched successfully.")
        return get_ticker_list(tickers=tickers)
    except Exception as e:
        logger.error(f"Error in get_ticker_info: {e} - {traceback.format_exc()}")
        return []

def check_and_update_trades():
    now = datetime.now()
    fifteen_minutes_ago = now - timedelta(minutes=cycle_period())

    # Veritabanındaki son 15 dakika içinde oluşturulmuş emirleri al
    trades = collection.find({"status":  {"$lt": 4}})

    for trade in trades:
        if trade['status'] in [1, 3]:  # 1: buy open, 3: sell open
            order_id = trade['buy_id'] if trade['status'] == 1 else trade['sell_id']
            try:
                order_info = exchange.fetchOrder(order_id, trade['symbol'])
                if order_info['filled'] >= order_info['amount']:
                    # Emir tamamen gerçekleşmiş, durumu güncelle
                    new_status = 2 if trade['status'] == 1 else 4  # 2: bought, 4: sold
                    collection.update_one({"_id": trade['_id']}, {"$set": {"status": new_status}})
                    logger.info(f"Trade status updated for {order_id}")
            except Exception as e:
                logger.error(f"Error in check_and_update_trades: {e} - {traceback.format_exc()}")


def read_config():
    with open("config.yaml", "r") as file:
        return yaml.safe_load(file)

def get_config():
    global config
    global ccxt_info
    global trade_parameters
    global settings

    new_config = read_config()
    if new_config != config:
        config = new_config
        logger.info("Yeni konfigürasyon dosyası yüklendi.")
    trade_parameters = config.get("trade_parameters", {})
    settings = config.get("settings", {})
    ccxt_info = config.get("ccxt", {})


def get_calculation_period_type(calculation_period_type):
    cpt = int(calculation_period_type)
    if cpt == 1:
        return 60
    elif cpt == 2:
        return 60 * 24
    elif cpt == 3:
        return 60 * 24 * 7
    else:
        return 1

def get_calculation_period_type_name(calculation_period_type,calculation_period):
    cpt = int(calculation_period_type)
    if cpt == 0:
        return str(calculation_period)+"m"
    elif cpt == 1:
        return str(calculation_period)+"h"
    elif cpt == 2:
        return str(calculation_period)+"d"
    elif cpt == 3:
        return str(calculation_period)+"w"
    else:
        return "15m"

def cycle_period():
    calculation_period = trade_parameters.get("calculation_period", 15)
    calculation_period_type = trade_parameters.get("calculation_period_type", 0)
    return calculation_period * get_calculation_period_type(calculation_period_type)

def initialize_database():
    global client
    global db
    global collection
    global config
    flag=True
    while flag:
        try:
            minfo = config.get("mongodb",{})
            client = MongoClient(minfo["uri"])
            db = client[minfo["db_name"]]
            collection = db[minfo["collection_name"]]
            flag=False
        except Exception as e:
            logger.error(f"Database initialization failed: {e} - config {minfo} - {traceback.format_exc()}")
            time.sleep(2)

def initialize_exchange():
    global exchange
    try:
        exchange_id = ccxt_info.get("exchange_id", "binance")
        
        exchange = getattr(ccxt, exchange_id)({
            'apiKey': ccxt_info.get("api_key", ""),
            'secret': ccxt_info.get("secret", ""),
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
            }
        })
        logger.info(f"Exchange initialized successfully.- {exchange.name}")
    except Exception as e:
        logger.error(f"Exchange initialization failed: {e} - {traceback.format_exc()}")
        

def is_trade_open(symbol):
    return collection.find_one({"symbol": symbol, "status": {"$lt": 4}}) is not None

def execute_buy_order(symbol, amount, price, amount_usdt, rsi):
    try:
        order = exchange.create_limit_buy_order(symbol, amount, price)
        collection.insert_one({
            "symbol": symbol,
            "buy_id": order["id"],
            "sell_id": "",
            "status": 1, # 1 means buy open , 2 bought ,3 sell open ,4 sold
            "entry_price": price,
            "entry_amount": amount,
            "entry_amount_usdt": amount_usdt,
            "entry_rsi": rsi,
            "entry_time": datetime.now(),
            "exit_time": None,
            "exit_price": None,
            "exit_amount": None,
            "exit_amount_usdt": None,
            "exit_rsi": None,
            "profit": None,
            "profit_percentage": None
        })
    except Exception as e:
        logger.error(f"symbol: {symbol}, amount:{amount}, price:{price}, rsi:{rsi}, amount_usdt:{amount_usdt} ,Error in execute_buy_order: {e} - {traceback.format_exc()}")



def execute_sell_order(symbol, amount, price):
    rsi=fetch_rsi(symbol=symbol,timeframe=timeframe)
    # logger.debug(f"sending sell order for {symbol} - amount: {amount} - price: {price} - rsi: {rsi}")
    try:
        order = exchange.create_limit_sell_order(symbol, amount, price)
        collection.update_one(
            {"symbol": symbol, "status": 2},
            {"$set": {"status": 3, "exit_time": datetime.now(), "sell_id": order["id"], 
                    "exit_price": price, "exit_amount": amount,"exit_amount_usdt":price*amount, "exit_rsi": rsi,
                    "profit":price*amount-collection.find_one({"symbol": symbol, "status": 2})["entry_amount_usdt"],
                    "profit_percentage":(1-((price*amount)/(collection.find_one({"symbol": symbol, "status": 2})["entry_amount_usdt"])))*100}}
        )
    except Exception as e:
        logger.error(f"symbol: {symbol}, amount:{amount}, price:{price}, rsi:{rsi}, Error in execute_sell_order: {e} - {traceback.format_exc()}")

def get_trades_with_status_2(symbol):
    trades = collection.find({"symbol": symbol, "status": 2})
    return list(trades)

def buy_option_check(symbol):
    rsi = fetch_rsi(symbol=symbol,timeframe=timeframe)
    # logger.info(f"RSI for {symbol} is {rsi}")
    if rsi < trade_parameters.get("RSI_BUY_LIMIT", 35):
        account_balance = exchange.fetch_balance()['free']['USDT']
        if account_balance < trade_parameters.get("MINIMUM_TRADE_AMOUNT",5.1):
            return
        if account_balance > trade_parameters.get("MAXIMUM_TRADE_AMOUNT",10):
            amount_to_buy = trade_parameters.get("MAXIMUM_TRADE_AMOUNT",10)
        else:
            amount_to_buy = account_balance
        # logger.info(f"Buying {amount_to_buy} {symbol} for {rsi} RSI. Account balance is {account_balance}")
        rejected_list=["BNB", "BSW","ETH","USDC","BUSD","FDUSD","TUSD","USDP"] 

        for i in rejected_list:
            if i in symbol:
                logger.info(f"{symbol} is in rejected list.")
                return

        asked_price = exchange.fetch_ticker(symbol)['ask']
        amount_to_buy_for_order = amount_to_buy / asked_price
        execute_buy_order(symbol, amount_to_buy_for_order, asked_price,amount_to_buy, rsi)
        logger.info(f"Buy order executed for {symbol}. Amount: {amount_to_buy_for_order}, Price: {asked_price}, Amount USDT: {amount_to_buy} , RSI: {rsi}")

def sell_check_criteria(symbol,current_price, trade):
    total_duration_check= 5 * cycle_period() * 60
    sell_profit1 = trade_parameters.get("sale_profit1", 1.07)
    sell_profit2 = trade_parameters.get("sell_profit2", 1.05)
    sell_profit3 = trade_parameters.get("sell_profit3", 1.04)
    sell_difference_rsi = trade_parameters.get("sell_difference_rsi", 32)
    
    rsi = fetch_rsi(symbol=trade["symbol"],timeframe=timeframe)
    # logger.info(f"Checking sell criteria for {symbol}. Current price: {current_price}, Entry price: {trade['entry_price']}, Entry RSI: {trade['entry_rsi']}, RSI: {rsi}")
    criterias = [
        ((current_price >= (trade["entry_price"] * sell_profit3)) and (rsi > (trade["entry_rsi"] + sell_difference_rsi))),
        ((current_price >= (trade["entry_price"] * sell_profit2)) and (datetime.now() - trade["entry_time"]).total_seconds()>= total_duration_check ),
        ((current_price >= (trade["entry_price"] * sell_profit1)) and rsi > 65) 

    ]
    return any(criterias)

def process_symbol(symbol_info):
    symbol=symbol_info["symbol"]
    volume=symbol_info["volume"]
    volume_limit = trade_parameters.get("volume_limit", 1000000)
    if volume < volume_limit:
        # logger.info(f"Volume of {symbol} is lower than {volume_limit}.")
        return
    check_and_update_trades()
    if not is_trade_open(symbol):
        # logger.info(f"Trade is not open for {symbol}.")
        # buy_enabled: True
        if trade_parameters.get("buy_enabled", True):
            buy_option_check(symbol)


    open_trades = get_trades_with_status_2(symbol)
    # logger.info(f"Open trades for {symbol}: {len(open_trades)}")
    for trade in open_trades:
        current_price = exchange.fetch_ticker(trade["symbol"])["bid"]
        if sell_check_criteria(symbol,current_price, trade):
            
            execute_sell_order(trade["symbol"], trade["entry_amount"], current_price)
            logger.info(f"Sold {trade['entry_amount']} {symbol} for {current_price}.")

def main():
    global exchange
    global config
    global collection
    global trade_parameters
    global settings
    global timeframe
    global volume_limit
    logger.info("Starting the main process.")
    get_config()
    initialize_database()
    initialize_exchange()
    count=0
    while True:
        try:
            count+=1
            start_time = time.perf_counter()
            if count % 15 == 1:
                get_config()
                period = cycle_period() * 60 # Saniye cinsinden
                
                timeframe = get_calculation_period_type_name(trade_parameters.get("calculation_period_type", 0),trade_parameters.get("calculation_period", 15))
                logger.info(f"Config reloaded and cycle period is set to {period} seconds.")
                count=0
           
            check_and_update_trades()
            if settings.get("use_multiprocessing",False):
                symbols = get_ticker_info()
                pool_size = cpu_count() * 4  # Her CPU için 4 ekstra süreç

                with Pool(pool_size) as pool:
                    pool.starmap(process_symbol, list(symbols))
                    logger.info("Processing symbols with multiprocessing.")

            else:
                symbols = get_ticker_info()
                logger.info("Processing symbols without multiprocessing.")
                for symbol in symbols:
                    process_symbol(symbol)
            check_and_update_trades()

            gecen_zaman=time.perf_counter()-start_time
            # if gecen_zaman < period:
            #     time.sleep(period - gecen_zaman)
            time.sleep(5)
            logger.info(f"-----------------------Cycle Ends-----------------------------gecen_zaman: {gecen_zaman} - period: {period}")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e} - {traceback.format_exc()}")
            time.sleep(10)  # Wait for a while before next iteration

if __name__ == "__main__":
    main()
