import time
import config
import pandas as pd
import ta
import indicators
import requests
import hmac
import hashlib
import sys
import json



CAN_OPEN_POSITION = 1

class MyTrade():
    def __init__(self, Order_Id,qty,side):
        self.open_position_order_id = str(Order_Id)
        self.buy_price = 0
        self.qty = qty
        self.side = side
        self.close_position_order_id = 0




base_url = 'https://fapi.binance.com'

header = {'X-MBX-APIKEY': config.API_Key}

def binance_future_limit(side,quantity,price):

    url = base_url+'/fapi/v1/order'
    timestamp = str(round(time.time())*1000)

    message = 'symbol=BTCUSDT&side='+side+'&type=LIMIT&timeInForce=GTC&quantity='+str(quantity)+'&price='+str(price)+'&timestamp='+timestamp

    signature = hmac.new(bytes(config.Secret_Key, 'latin-1'), msg=bytes(message, 'latin-1'),
                         digestmod=hashlib.sha256).hexdigest().upper()

    params = message + '&signature='+signature

    # call api
    order_update = requests.post(url,headers=header,params= params)
    # print(order_update.json())
    order_update = order_update.json()

    order_details = MyTrade(order_update['orderId'],quantity,side)

    return order_details

def binance_future_trailing_stoploss(trade,activationPrice,callbackRate):
    url = base_url + '/fapi/v1/order'
    timestamp = str(round(time.time()) * 1000)

    if trade.side == 'BUY':
        new_side = 'SELL'
    else:
        new_side = 'BUY'
    message = 'symbol=BTCUSDT&side='+str(new_side)+'&type=TRAILING_STOP_MARKET&quantity='+str(trade.qty)+'&activationPrice='+str(activationPrice)+'&callbackRate='+str(callbackRate)+'&timestamp='+timestamp

    signature = hmac.new(bytes(config.Secret_Key, 'latin-1'), msg=bytes(message, 'latin-1'),
                         digestmod=hashlib.sha256).hexdigest().upper()

    params = message + '&signature=' + signature

    # call api
    order_update = requests.post(url, headers=header, params=params)
    order_update = order_update.json()
    print(order_update)
    trade.close_position_order_id = order_update['orderId']
    return 1

def binance_query_order(trade):

    url = base_url+'/fapi/v1/order'
    timestamp = str(round(time.time()) * 1000)

    if trade.close_position_order_id != 0:
        while(True):

            message = 'symbol=BTCUSDT&timestamp=' + timestamp + '&orderId=' + str(trade.close_position_order_id)

            signature = hmac.new(bytes(config.Secret_Key, 'latin-1'), msg=bytes(message, 'latin-1'),
                                 digestmod=hashlib.sha256).hexdigest().upper()

            params = message + '&signature=' + signature

            order_update = requests.get(url, headers=header, params=params)
            order_update = order_update.json()

            status = order_update['status']

            if status == 'FILLED':
                global CAN_OPEN_POSITION
                CAN_OPEN_POSITION = 1
                break


    while(True):
        # call api

        message = 'symbol=BTCUSDT&timestamp=' + timestamp + '&orderId=' + str(trade.open_position_order_id)

        signature = hmac.new(bytes(config.Secret_Key, 'latin-1'), msg=bytes(message, 'latin-1'),
                             digestmod=hashlib.sha256).hexdigest().upper()

        params = message + '&signature=' + signature


        order_update = requests.get(url, headers=header, params=params)
        order_update = order_update.json()
        # print(order_update)

        if trade.side == 'BUY':
            operator = 1
        else:
            operator = -1

        status = order_update['status']
        activationPrice = int(trade.buy_price) + operator*40
        callbackRate = 0.1
        if status == 'FILLED':
            print("Order filled subsequent order placed ")
            trade.buy_price = order_update['avgPrice']
            trade.qty = order_update['executedQty']
            response = binance_future_trailing_stoploss(trade,activationPrice,callbackRate)

            if response == 1:
                print("Sucessfully placed ")
            break



def binance_future_markprice():
    url = base_url + '/fapi/v1/premiumIndex'
    timestamp = str(time.time() * 1000)

    params = 'symbol=BTCUSDT'

    response = requests.get(url,headers=header,params= params)
    response = eval(response.text)
    print(response['markPrice'])
    return response['markPrice']


def heikin_ashi(df):
    heikin_ashi_df = pd.DataFrame(index=df.index.values, columns=['open', 'high', 'low', 'close','Open time','Close time','Number of trades','Quote asset volume'])



    heikin_ashi_df['close'] = (pd.to_numeric(df['open']) + pd.to_numeric(df['high']) + pd.to_numeric(df['low']) + pd.to_numeric(df['close'])) / 4

    for i in range(len(df)):
        if i == 0:
            heikin_ashi_df.iat[0, 0] = pd.to_numeric(df['open'].iloc[0])
        else:
            heikin_ashi_df.iat[i, 0] = (pd.to_numeric(heikin_ashi_df.iat[i - 1, 0]) +pd.to_numeric(heikin_ashi_df.iat[i - 1, 3])) / 2

    heikin_ashi_df['high'] = heikin_ashi_df.loc[:, ['open', 'close']].join(df['high']).max(axis=1)

    heikin_ashi_df['low'] = heikin_ashi_df.loc[:, ['open', 'close']].join(df['low']).min(axis=1)

    heikin_ashi_df['Open time'] = df['Open time']
    heikin_ashi_df['Close time'] = df['Close time']
    heikin_ashi_df['Quote asset volume'] = df['Quote asset volume']
    heikin_ashi_df['Number of trades'] = df['Number of trades']

    return heikin_ashi_df


def new_stratergy():
    global CAN_OPEN_POSITION
    while(True):
        data = requests.get('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=1000')

        df = pd.DataFrame(eval(data.text))

        df.columns = ['Open time', 'open', 'high', 'low', 'close', 'Volume', 'Close time', 'Quote asset volume',
                      'Number of trades', 'tbbav', 'tbqav', 'ignore']


        new_df = heikin_ashi(df)
        pd.set_option('display.max_columns', None)

        #bollinger calculations
        bollinger_band = ta.volatility.BollingerBands(new_df['open'],14,1.6)

        bb_hband = bollinger_band.bollinger_hband()
        bb_lband = bollinger_band.bollinger_lband()

        #rsi calculations
        rsi_close = ta.momentum.RSIIndicator(new_df['close'],14)
        rsi_close = rsi_close.rsi()

        rsi_open = ta.momentum.RSIIndicator(new_df['open'], 14)
        rsi_open = rsi_open.rsi()


        new_df = indicators.SuperTrend(new_df,10,3,ohlc=['open','high','low','close'])


        new_df['rsi_close'] = rsi_close.values
        new_df['rsi_open'] = rsi_open.values
        new_df['rsi_diff'] = new_df['rsi_close'] - new_df['rsi_open']
        new_df['bb_hband'] = bb_hband.values
        new_df['bb_lband'] = bb_lband.values

        # new_df.to_csv('analysis_csv.csv',index=False,header=True)
        print(new_df.tail(2))

        #essential values
        current_open= new_df['open'][999]
        current_rsi_open = new_df['rsi_open'][999]
        current_bb_hband = new_df['bb_hband'][999]
        current_bb_lband = new_df['bb_lband'][999]
        current_volume = new_df['Quote asset volume'][998]
        current_trend = new_df['STX_10_3'][999]
        current_trend_indicator = new_df['ST_10_3'][999]

        if current_open > current_bb_hband: #and current_volume/current_open > 800:
            side = 'BUY'
            quantity=0.03

            if current_rsi_open > 69 and CAN_OPEN_POSITION == 1:

                CAN_OPEN_POSITION = 0
                if current_trend == 'up':
                    market_price = binance_future_markprice()
                    market_price = round(float(market_price),2)
                    limit_price = market_price+((market_price*0.04)/100)
                    print("LONG order placing")
                    trade_details = binance_future_limit(side,quantity,limit_price)
                    binance_query_order(trade_details)

        if current_open < current_bb_lband: # and current_volume/current_open > 800:

            if current_rsi_open < 31 and CAN_OPEN_POSITION == 1:

                CAN_OPEN_POSITION = 0
                side = 'SELL'
                quantity = 0.03
                if current_trend == 'down':
                    market_price = binance_future_markprice()
                    market_price = round(float(market_price), 2)
                    limit_price = market_price + ((market_price * 0.04) / 100)
                    print("SHORT order placing")
                    trade_details = binance_future_limit(side, quantity, limit_price)
                    binance_query_order(trade_details)

        time.sleep(300)


print("Program triggered !!! ")


while(True):

    if time.time()*1000 >= int(sys.argv[1]):
        print("Program started !!! ")
        new_stratergy()
        break
