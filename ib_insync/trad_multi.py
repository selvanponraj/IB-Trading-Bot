from ib_insync import *
import asyncio
import pandas as pd
import threading
import time
from datetime import datetime, timedelta, timezone
import nest_asyncio
nest_asyncio.apply()
import numpy as np

import datetime as dt
import os

import os
# 50 stocks
# tickers = 'NIO AAL CCL BLNK JMIA NCLH SNAP DKNG PLUG WKHS SONO FE OXY WORK NKLA FEYE PCG UBER UAL INO MRNA SBE LYFT TWTR IQ JWN DVN BILI CIIC MGM SPWR GME KSS NUAN VIPS BLDP HST DISCA LVS HAL LB FTCH SAVE CNK SPG HUYA NOV SDC NET EQT'
tickers = ['EURUSD']
contracts = [Forex(pair) for pair in ('EURUSD', 'USDJPY', 'GBPUSD', 'USDCHF', 'USDCAD')]

# no_of_API_requests = 50
# tickers=pd.read_csv("S&P500.csv").Symbol.tolist()
# tickers=list(np.setdiff1d(tickers,['BRK.B','BF.B', 'ABNB'], assume_unique=True))

freq = "1 min"
window = 1
units = 1000
end_time = (dt.datetime.utcnow() + dt.timedelta(seconds = 15)).time() # stop condition (5.5 mins from now)
sl_perc = 0.1
tp_perc = 0.1

class Trader:
    def __init__(self, contract):
        self.contract = contract
        ib.errorEvent += self.onError

    def onError(self, reqId, errorCode, errorString, contract):
        print({'ticker': self.contract.localSymbol, 'errorCode': errorCode, 'reqId': reqId, 'errorString': errorString, 'contract': contract})
        pass
    
    def onBarUpdate(self,bars, hasNewBar): 
        global df, last_bar, last_update

        last_update = dt.datetime.utcnow()
        
        if bars[-1].date > last_bar: 
            last_bar = bars[-1].date
        
            # Data Processing
            df = pd.DataFrame(bars)[["date", "open", "high", "low", "close"]].iloc[:-1] 
            df.set_index("date", inplace = True)
            
            ####################### Trading Strategy ###########################
            # df = df[["close"]].copy()
            # df["returns"] = np.log(df["close"] / df["close"].shift())
            # df["position"] = -np.sign(df.returns.rolling(window).mean())
            sma_s = 2
            sma_l = 5
            df = df[["close"]].copy()
            df["sma_s"] = df.close.rolling(sma_s).mean()
            df["sma_l"] = df.close.rolling(sma_l).mean()
            df.dropna(inplace = True)
            df["position"] = np.where(df["sma_s"] > df["sma_l"], 1, -1 )

            # M- Pattern: SELL -1
            # W- Pattern  BUY +1
            ####################################################################
            
            # Trading
            target = df["position"][-1] * units
  
            execute_trade_basic(self.contract,target = target)
            # execute_trade(self.contract,target = target)
            # Display
            # os.system('clear')
            # print(df)
        else:
            try:
                trade_reporting(self.contract)
            except:
                pass

    async def _init(self):
        global bars, last_bar
        print('{} started {}'.format(datetime.now().strftime('%H:%M:%S'), self.contract.localSymbol))
        c = 0
        if self.contract.secType == 'CFD':
            contract = Forex(self.contract.symbol+self.contract.currency)
        else:
            contract = self.contract

        while 1:
            if dt.datetime.utcnow().time() >= end_time: 
                ib.cancelHistoricalData(bars) # stop stream
                return None
            c += 1
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime='',
                durationStr='900 S',
                barSizeSetting='10 secs',
                whatToShow='MIDPOINT',
                useRTH=True,
                formatDate=1,
                keepUpToDate=True)
            try:
                last_bar = bars[-1].date
                bars.updateEvent += self.onBarUpdate
            except (AttributeError):
                print('{} {} AttributeError'.format(datetime.now().strftime('%H:%M:%S'), self.contract.localSymbol))
            except Exception as e:
                print('{} {} error: {}'.format(datetime.now().strftime('%H:%M:%S'), self.contract.localSymbol, e))
                if c == 5:
                    return None
                await asyncio.sleep(1)
            except:
                print('{} {} error'.format(datetime.now().strftime('%H:%M:%S'), self.contract.localSymbol))

def execute_trade(contract,target):
    global exp_pos
        
    # 1. identify required trades
    trades = target - exp_pos
    
    # 2. determine SL Price and TP Price
    current_price = df.close.iloc[-1]

    if sl_perc:
        if target > 0: # LONG
            sl_price = round(current_price * (1 - sl_perc), 4) 
        elif target < 0: # SHORT
            sl_price = round(current_price * (1 + sl_perc), 4)      
    else: 
        sl_price = None

    if tp_perc:
        if target > 0: # LONG
            tp_price = round(current_price * (1 + tp_perc), 4) 
        elif target < 0: # SHORT
            tp_price = round(current_price * (1 - tp_perc), 4)      
    else: 
        tp_price = None

    print(contract.localSymbol, target, exp_pos,trades)
        
    # 3. trade execution
    if target > 0: # GOING LONG
        if current_pos == 0: # from NEUTRAL
            go_long_short(contract,side = "BUY", target = target, sl_price = sl_price, tp_price = tp_price) 
        elif current_pos < 0: # from SHORT:
            cancel_orders() # cancel sl/tp orders
            go_neutral(contract,side = "BUY", trades = current_pos)
            go_long_short(contract,side = "BUY", target = target, sl_price = sl_price, tp_price = tp_price)
    elif target < 0: # GOING SHORT
        if current_pos == 0: # from NEUTRAL  
            go_long_short(contract,side = "SELL", target = abs(target), sl_price = sl_price, tp_price = tp_price) 
        elif current_pos > 0: # from LONG
            cancel_orders() # cancel sl/tp orders
            go_neutral(contract,side = "SELL", trades = current_pos)
            go_long_short(contract,side = "SELL", target = abs(target), sl_price = sl_price, tp_price = tp_price)
    else: # GOING NEUTRAL
        print('NEUTRAL', current_pos)
        
        if current_pos < 0: # from SHORT
            cancel_orders() # cancel sl/tp orders
            go_neutral(contract,side = "BUY", trades = current_pos)
        elif current_pos > 0: # from LONG:
            cancel_orders() # cancel sl/tp orders
            go_neutral(contract,side = "SELL", trades = current_pos)
    exp_pos = target
    
def go_long_short(contract,side, target, sl_price, tp_price): # NEW Go Long/Short starting from Neutral position
    bracket = BracketOrder(parentOrderId = ib.client.getReqId(), 
                           childOrderId1 = ib.client.getReqId(), 
                            childOrderId2 = ib.client.getReqId(),
                            action = side,
                            quantity = target,
                            stopLossPrice = sl_price, 
                            takeProfitPrice = tp_price,
                          )
    for o in bracket:
        order = ib.placeOrder(contract, o)
    
def go_neutral(contract,side, trades): # Close Long/Short position
    order = MarketOrder(side, abs(trades))
    trade = ib.placeOrder(contract, order)    
    
def cancel_orders(): # cancel SL/TP orders
    try:
        print("SL Cancel", stopLoss)
        sl_cancel = ib.cancelOrder(stopLoss)
    except Exception as e:
        print("Inside Error", e)
        raise e
        # pass
    try:
        print("TP Cancel", takeProfit)
        tp_cancel = ib.cancelOrder(takeProfit)
    except Exception as e:
        print("Inside Error", e)
        raise e
        # pass 

def BracketOrder(parentOrderId, childOrderId1, childOrderId2,
                 action, quantity, stopLossPrice, takeProfitPrice):
    global stopLoss, takeProfit
    
    # Market Order (parent) - GO LONG or GO SHORT
    parent = Order()
    parent.orderId = parentOrderId
    parent.action = action
    parent.orderType = "MKT"
    parent.totalQuantity = quantity
    if not stopLossPrice and not takeProfitPrice: 
        parent.transmit = True
    else:
        parent.transmit = False
        
    bracketOrder = [parent]

    if stopLossPrice:
        # attached Stop Loss Order (child) 
        stopLoss = Order()
        stopLoss.orderId = childOrderId1
        stopLoss.action = "SELL" if action == "BUY" else "BUY"
        stopLoss.orderType = "STP"
        stopLoss.auxPrice = stopLossPrice
        stopLoss.totalQuantity = quantity
        stopLoss.parentId = parentOrderId
        if not takeProfitPrice: 
            stopLoss.transmit = True
        else:
            stopLoss.transmit = False
        bracketOrder.append(stopLoss)
    
    if takeProfitPrice:
        # attached Take Profit Order (child)
        takeProfit = Order()
        takeProfit.orderId = childOrderId2
        takeProfit.action = "SELL" if action == "BUY" else "BUY"
        takeProfit.orderType = "LMT"
        takeProfit.totalQuantity = quantity
        takeProfit.lmtPrice = takeProfitPrice
        takeProfit.parentId = parentOrderId
        takeProfit.transmit = True
        bracketOrder.append(takeProfit)
        
    return bracketOrder     
def execute_trade_basic(contract,target):
    global current_pos
    conID = contract.conId
    # 1. get current Position
    try:
        current_pos = [pos.position for pos in ib.positions() if pos.contract.conId == conID][0]
    except:
        current_pos = 0

    # 2. identify required trades
    trades = target - current_pos
    
    print("Order: " , contract.localSymbol, current_pos, target, trades)
    
    # 3. trade execution
    if trades > 0:
        side = "BUY"
        order = MarketOrder(side, abs(trades))
        trade = ib.placeOrder(contract, order)  
    elif trades < 0:
        side = "SELL"
        order = MarketOrder(side, abs(trades))
        trade = ib.placeOrder(contract, order)
    else:
        pass

def trade_reporting():
    global report

    fills = ib.fills()
    ib.sleep(0.1)
    # start = (pd.to_datetime("today")+pd.DateOffset(days=-1)).strftime('%Y-%m-%d')
    start = pd.to_datetime("today").strftime('%Y-%m-%d')
    # fill_df = util.df([fs.execution for fs in fills()])[["execId", "time", "side", "cumQty", "avgPrice"]].set_index("execId")
    # profit_df = util.df([fs.commissionReport for fs in fills()])[["execId", "realizedPNL"]].set_index("execId")
    
    # report= pd.concat([fill_df, profit_df], axis = 1).set_index("time").sort_index(ascending=True)
    cols = ["time", "symbol", "side", "cumQty", "avgPrice", "realizedPNL"]
    report = pd.DataFrame([[
                            fill.execution.time,
                            fill.contract.localSymbol,
                            fill.execution.side,
                            fill.execution.cumQty,
                            fill.execution.avgPrice,
                            fill.commissionReport.realizedPNL,
                            ]
                            for fill in fills ], columns=cols).set_index("time").sort_index(ascending=True)
    

    report = report.loc[report.index > start]
    report = report.groupby("time").agg({"symbol":"first","side":"first", "cumQty":"max", "avgPrice":"mean", "realizedPNL":"sum"})
    report["cumPNL"] = report.realizedPNL.cumsum()
    os.system('clear')
    print(report)

async def fetch_tickers():
    return await asyncio.gather(*(asyncio.ensure_future(safe_trader(contract)) for contract in contracts))

async def safe_trader(contract):
    async with sem:
        t = Trader(contract)
        return await t._init()
    
def get_sp500_contracts():
    # payload=pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    # pd.DataFrame(payload[0]).to_csv("S&P500.csv")
    pd.read_csv("S&P500.csv")
    stocklist=pd.read_csv("S&P500.csv").Symbol.tolist()
    contracts = [Stock(symbol=eachstock, exchange='SMART', currency='USD')
                for eachstock in stocklist]    
    return contracts

def get_forex_contacts():
    contracts = [Forex(pair) for pair in ('EURUSD', 'USDJPY', 'GBPUSD', 'USDCHF', 'USDCAD')]
    return contracts

def get_forex_cfd_contacts():
    contracts = [CFD('EUR', currency = 'USD'),CFD('GBP', currency = 'USD')]
    return contracts
def get_index_cfd_contacts():
    contracts = [CFD('IBUS30'),CFD('IBUS500'), CFD('IBUS500')]
    return contracts

if __name__ == '__main__':
    
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=201) # 7496, 7497, 4001, 4002
    contracts = ib.qualifyContracts(*get_forex_cfd_contacts())
    # print(contracts)
    
    global last_update, session_start, exp_pos, current_pos

    exp_pos = 0 
    current_pos = 0
    last_update = dt.datetime.utcnow()
    session_start = pd.to_datetime(last_update).tz_localize("utc")

    
    try:
        start_time = time.time()
        print('{} start time'.format(datetime.now().strftime('%H:%M:%S')))
        sem = asyncio.Semaphore(50)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(fetch_tickers())
        print("%.2f execution seconds" % (time.time() - start_time))

        # stop trading session
        while True:
            ib.sleep(5) # check every 5 seconds
            if dt.datetime.utcnow().time() >= end_time: # if stop conditions has been met
                for contract in contracts:
                    # execute_trade_basic(contract,target = 0) # close open position
                    execute_trade(contract,target = 0) # close open position
                    ib.sleep(10)
                # try:
                #     trade_reporting() # final reporting
                # except Exception as e:
                #     print(e)
                print("Session Stopped.")
                ib.disconnect()
                break
            else:
                pass
    except (KeyboardInterrupt, SystemExit):
        ib.disconnect()