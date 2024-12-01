from ib_insync import IB, Stock, CFD
from ib_insync import MarketOrder

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

# Create a stock contract with specific details
contract = CFD(
    symbol='IBDE40', 
)

# Verify contract details
print(contract)

# Optionally, you can use the contract to request market data or place an order
# Example: Request market data
ib.qualifyContracts(contract)
# Request historical data
bars = ib.reqHistoricalData(
    contract,
    endDateTime='',
    durationStr='1 D',
    barSizeSetting='5 mins',
    whatToShow='MIDPOINT',
    useRTH=True
)

# Print historical data
for bar in bars:
    print(f'Time: {bar.date} Open: {bar.open} High: {bar.high} Low: {bar.low} Close: {bar.close}')

# ticker = ib.reqMktData(contract)
# ib.sleep(10)  # Allow time for data to come through
# print(f"Market price for {contract.symbol}: {ticker.last}")

# Place an order

order = MarketOrder('BUY', 1)
trade = ib.placeOrder(contract, order)

# Wait for the order to be filled
while not trade.isDone():
    ib.sleep(1)

print(f'Order status: {trade.orderStatus.status}')
# Disconnect from IBKR
ib.disconnect()