from ib_insync import IB, Stock, MarketOrder, StopOrder, LimitOrder
import pandas as pd
import math
import os
import logging
from datetime import datetime
import csv

# Configure logging
yahoo_today = datetime.now().strftime('%Y%m%d')

log_file_path = f"zen-{datetime.now().strftime('%Y-%m-%d')}.log"
# Function to write log entries
log_directory = os.path.join(os.path.dirname(__file__), 'log')
os.makedirs(log_directory, exist_ok=True)
log_file_path = os.path.join(log_directory, f"zen-{datetime.now().strftime('%Y-%m-%d')}.log")

def write_log(message):
    with open(log_file_path, 'a') as log_file:
        log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
# Function to write trade entries
trade_directory = os.path.join(os.path.dirname(__file__), 'trade')
os.makedirs(trade_directory, exist_ok=True)
trade_filename = os.path.join(trade_directory, f"zen-trade-{datetime.now().strftime('%Y-%m-%d')}.csv")
# Write header to trade file if it doesn't exist or is empty
if not os.path.isfile(trade_filename) or os.stat(trade_filename).st_size == 0:
    with open(trade_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Symbol', 'Trade Date', 'Purchase Price', 'Quantity', 'Commission'])

def write_trade(ticker, trade_date, market_price, quantity, commission):
    with open(trade_filename, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([ticker, trade_date, market_price, quantity, commission])

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # TWS or IB Gateway must be running
risk_amount = 50  # Risk amount per trade
# Load the CSV file
# csv_file = 'orders.csv'
# df = pd.read_csv(csv_file)
# Example usage
# file_path = 'zen.csv'  # Replace with the path to your file containing tickers

def read_tickers_from_file(file_path):
    with open(file_path, 'r') as file:
        # Read content and strip any leading/trailing whitespaces or newlines
        content = file.read().strip()
        
        # Split the content into tickers based on commas or newlines
        tickers = [ticker.strip() for ticker in content.replace(',', '\n').splitlines()]
        
    return tickers

# Function to calculate ATR (simple example based on IBKR historical data)
def fetch_5min_data(contract, duration='2 D'):
    """
    Fetch 5-minute historical data for the given stock symbol.
    """
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=duration,  # Duration (e.g., '2 D' for 2 days of data)
        barSizeSetting='5 mins',  # 5-minute bars
        whatToShow='TRADES',
        useRTH=True,  # Use regular trading hours
        formatDate=1
    )
    return pd.DataFrame(bars)

def calculate_day_atr(contract, period='14 D'):
    """
    Calculate the ATR for daily candlestick data.
    """
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=period,  # Duration (e.g., '14 D' for 14 days of data)
        barSizeSetting='1 day',  # Daily bars
        whatToShow='TRADES',
        useRTH=True,  # Use regular trading hours
        formatDate=1
    )
    data = pd.DataFrame(bars)
    data['Prev Close'] = data['close'].shift(1)
    data['TR'] = data.apply(
        lambda row: max(
            row['high'] - row['low'],  # High - Low
            abs(row['high'] - row['Prev Close']),  # High - Previous Close
            abs(row['low'] - row['Prev Close'])  # Low - Previous Close
        ),
        axis=1
    )
    data['ATR'] = data['TR'].rolling(window=14).mean()
    return data

def calculate_atr(data, period=14):
    """
    Calculate ATR for the given DataFrame of 5-minute candlestick data.
    """
    data['Prev Close'] = data['close'].shift(1)
    data['TR'] = data.apply(
        lambda row: max(
            row['high'] - row['low'],  # High - Low
            abs(row['high'] - row['Prev Close']),  # High - Previous Close
            abs(row['low'] - row['Prev Close'])  # Low - Previous Close
        ),
        axis=1
    )
    # Calculate ATR as SMA of TR
    data['ATR'] = data['TR'].rolling(window=period).mean()
    return data

# Function to calculate quantity based on risk
def calculate_quantity(risk_amount, entry_price, stop_loss_price):
    risk_per_share = abs(entry_price - stop_loss_price)
    if risk_per_share <= 0:
        raise ValueError("Stop-loss price must be different from the entry price.")
    quantity = risk_amount / risk_per_share
    return math.floor(quantity)  # Round down to the nearest whole number


# Create a bracket order function
def create_bracket_order(action, quantity, stop_loss_price, take_profit_price):
    """
    Creates a bracket order with a parent market order and two child orders: stop-loss and take-profit.
    """
    # Parent Order (Market Order)
    parent_order = MarketOrder(action, quantity)
    parent_order.transmit = False  # Delay transmission until child orders are linked

    # Generate a unique ID for the parent order
    parent_order.orderId = ib.client.getReqId()  

    # Stop-Loss Order
    stop_loss_order = StopOrder('SELL', quantity, stop_loss_price)
    stop_loss_order.parentId = parent_order.orderId
    stop_loss_order.transmit = False

    # Take-Profit Order
    take_profit_order = LimitOrder('SELL', quantity, take_profit_price)
    take_profit_order.parentId = parent_order.orderId
    take_profit_order.transmit = True  # This transmits all orders in the bracket

    return [parent_order, stop_loss_order, take_profit_order]


# Read tickers and create a list
# Get all CSV files starting with 'zen-' in the directory
directory = os.path.dirname(__file__)

csv_files = [f for f in os.listdir(directory) if f.startswith('zen-') and f.endswith('.csv')]
# Read tickers from each CSV file and combine them into a single list

for csv_file in csv_files:
    ib.sleep(2)
    file_path = os.path.join(directory, csv_file)

    symbol_list = read_tickers_from_file(file_path)

    positions = ib.positions()

    # Extract the symbols from existing positions
    existing_symbols = [pos.contract.symbol for pos in positions]

    # Filter out symbols that already exist in positions
    filtered_symbols = [symbol for symbol in symbol_list if symbol not in existing_symbols]

    # Log the results
    write_log(f"{csv_file} : {filtered_symbols} @ {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

    # Place bracket orders for each ticker

    for ticker in filtered_symbols:
        # Create stock contract
        contract = Stock(ticker, 'SMART', 'USD')

        ib.qualifyContracts(contract)
        
        # Calculate ATR and determine stop-loss price
        data = fetch_5min_data(contract, duration='2 D')

        # Calculate ATR for the 5-minute candles
        # data = calculate_atr(data, period=14)
        data=calculate_day_atr(contract, period='14 D')

        # Display the latest ATR value
        atr = data['ATR'].iloc[-1]

        if atr is not None:
            stop_loss = atr
            take_profit = atr * 2
            
            print(f"{ticker} ATR: {atr}, Stop-Loss Adjustment: {stop_loss}")
            
            # Fetch the market price for calculating the stop-loss and take-profit levels
            ticker_data = ib.reqMktData(contract)
            # Wait for the data to populate (up to a few seconds)
            ib.sleep(2)

            # Use the last price, or fallback to close price from historical data
            market_price = ticker_data.last if ticker_data.last else ticker_data.close
            if math.isnan(market_price):
                market_price = 100
            market_price = round(market_price, 2)
            stop_loss_price = round(market_price - stop_loss,2)
            take_profit_price = round(market_price + take_profit,2)
            
            

            # stop_loss_price = round(market_price - (1.5 * atr), 2)
            # take_profit_price = round(market_price + take_profit, 2)

            if stop_loss_price >= market_price:
                print("Stop-Loss price is invalid: Must be below the market price for a SELL order.")
                continue

            quantity = calculate_quantity(risk_amount, market_price, stop_loss_price)
            if quantity <= 0:
                print("Quantity is invalid. Skipping order.")
                continue
            
            # print(f"Calculated Quantity: {quantity}")
            # Create and place a bracket order
            bracket = create_bracket_order('BUY', quantity, stop_loss_price, take_profit_price)
            for order in bracket:
                ib.placeOrder(contract, order)
                ib.sleep(2)
           
            # Fetch the actual filled price
            filled_orders = ib.fills()
            actual_filled_price = None
            total_price = 0
            total_quantity = 0
            commission = 0

            for fill in filled_orders:
                if fill.contract.symbol == ticker:
                    total_price += fill.execution.price * fill.execution.shares + fill.commissionReport.commission
                    total_quantity += fill.execution.shares
                    commission = fill.commissionReport.commission

            if total_quantity > 0:
                actual_filled_price = round(total_price / total_quantity,2)
            
            total_price = quantity * market_price

            write_trade(ticker, yahoo_today, actual_filled_price, quantity, commission)
            write_log(f"Bracket Order placed for {ticker}: Quantity: {quantity}, Market Price: {market_price}, Filled Price: {actual_filled_price}, Stop-Loss: {stop_loss_price}, Take-Profit: {take_profit_price}, Total-Price: {total_price}")
            print(f"Bracket Order placed for {ticker}: Quantity: {quantity}, Market Price: {market_price}, Filled Price: {actual_filled_price}, Stop-Loss: {stop_loss_price}, Take-Profit: {take_profit_price}, Total-Price: {total_price}")
        else:
            print(f"ATR not available for {ticker}. Order skipped.")
# Disconnect from IBKR
write_log("----------------------------------------------------------------------------------------")

# Log the trade details

# # Fetch positions again to get the updated list after placing orders
# positions = ib.positions()

# # Log the trade details for each position
# for pos in positions:
#     if pos.contract.symbol in filtered_symbols:
#         # Fetch commission report for the position
#         commission_report = ib.reqCompletedOrders(apiOnly=False)

#         # Find the commission for the current position
#         commission = 0
#         for report in commission_report:
#             if report.contract.symbol == pos.contract.symbol:
#                 commission = report.commissionReportEvent.commission
#                 break

#         write_trade(
#             pos.contract.symbol,
#             yahoo_today,
#             pos.position,
#             pos.avgCost,
#             commission
#         )
# ib.disconnect()
