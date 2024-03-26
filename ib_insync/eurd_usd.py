from ib_insync import *
# util.startLoop()  # uncomment this line when in a notebook
import pandas as pd
import numpy as np
import datetime as dt

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

contract = Forex('EURUSD')

# contract=Future('ES', '20240621', 'CME')

# contract = Stock('ABNB', 'SMART', 'USD')

# Contract(conId=270639)
# Stock('AMD', 'SMART', 'USD')
# Stock('INTC', 'SMART', 'USD', primaryExchange='NASDAQ')
# Forex('EURUSD')
# contract=CFD('IBUS30')
# Future('ES', '20180921', 'GLOBEX')
# Option('SPY', '20170721', 240, 'C', 'SMART')
# Bond(secIdType='ISIN', secId='US03076KAA60');

# contract = Stock('TSLA', 'SMART', 'USD')

# contract = Forex('EURUSD')

# Contract contract = new Contract()
# contract.Symbol = "ETH"
# contract.SecType = "CRYPTO";
# contract.Exchange = "PAXOS";
# contract.Currency = "USD";

# gold_cfd_contract = CFD('XAUUSD')


# def get_sp500_contracts():
#     payload=pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
#     pd.DataFrame(payload[0]).to_csv("S&P500.csv")
#     pd.read_csv("S&P500.csv")
#     stocklist=np.array_split(pd.read_csv("S&P500.csv").Symbol.tolist(), 50)
#     for eachstocklist in stocklist:
#         if len(eachstocklist) <= 45:                
#             contracts = [Stock(symbol=eachstock, exchange='SMART', currency='USD')
#                         for eachstock in eachstocklist]    
#     return contracts



# contracts = [CFD('EUR', currency = 'USD'), CFD('XAUUSD'), Forex('EURUSD')]
# contracts = [CFD('IBUS30'),CFD('IBUS500'), CFD('IBUS500')]

# ib.qualifyContracts(*contracts)

def onBarUpdate(bars, hasNewBar):
    df = util.df(bars)
    print(df)

# print(contracts)
bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='900 S',
        barSizeSetting='10 secs',
        whatToShow='MIDPOINT',
        useRTH=True,
        formatDate=1,
        keepUpToDate=True)

bars.updateEvent += onBarUpdate
print(util.df(bars))
# ib.run()
# while True:
#     ib.sleep(5)
#     print('Waiting 5 Seconds')
#     print(util.df(bars))
   






ib.cancelHistoricalData(bars)
ib.sleep(10)
ib.disconnect

