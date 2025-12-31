"""
30-Minute High Breakout Strategy
================================
Entry: Break of today's first 30-min bar high (9:30-10:00 AM)
Stop Loss: 1.5 × ATR below entry
Target 1: 2 × Risk (sell 50% of position)
Target 2: Trail with Daily 10-SMA (remaining 50%)
"""

from ib_insync import IB, Stock, MarketOrder, StopOrder, LimitOrder
import pandas as pd
import math
import os
from datetime import datetime, time
import csv

# ============================================================================
# CONFIGURATION
# ============================================================================
RISK_AMOUNT = 250  # Risk amount per trade in USD
ATR_MULTIPLIER = 1.5  # Stop loss = ATR * this multiplier
TARGET_RISK_MULTIPLE = 2  # Target 1 = Risk * this value
SMA_PERIOD = 10  # Period for trailing SMA stop
ATR_PERIOD = 14  # Period for ATR calculation

# IBKR Connection
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 7497  # 7497 for TWS, 4001 for IB Gateway
CLIENT_ID = 301

# ============================================================================
# LOGGING SETUP
# ============================================================================
log_directory = os.path.join(os.path.dirname(__file__), 'log')
os.makedirs(log_directory, exist_ok=True)
log_file_path = os.path.join(log_directory, f"daily3up-{datetime.now().strftime('%Y-%m-%d')}.log")

trade_directory = os.path.join(os.path.dirname(__file__), 'trade')
os.makedirs(trade_directory, exist_ok=True)
trade_filename = os.path.join(trade_directory, f"daily3up-trade-{datetime.now().strftime('%Y-%m-%d')}.csv")

def write_log(message):
    """Write a log entry with timestamp."""
    with open(log_file_path, 'a') as log_file:
        log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    print(f"[LOG] {message}")

def write_trade(ticker, entry_price, quantity, stop_loss, target1, target2_info):
    """Write trade entry to CSV file."""
    if not os.path.isfile(trade_filename) or os.stat(trade_filename).st_size == 0:
        with open(trade_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Symbol', 'Trade Date', 'Entry Price', 'Quantity', 'Stop Loss', 'Target 1', 'Target 2 Info'])
    
    with open(trade_filename, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([ticker, datetime.now().strftime('%Y-%m-%d %H:%M'), entry_price, quantity, stop_loss, target1, target2_info])

# ============================================================================
# DATA FUNCTIONS
# ============================================================================
def fetch_todays_30min_high(ib, contract):
    """
    Fetch today's first 30-minute bar high (9:30-10:00 AM).
    Returns the high price of that bar.
    """
    ib.qualifyContracts(contract)
    
    # Fetch 30-minute bars for today
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='1 D',
        barSizeSetting='30 mins',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )

    if not bars:
        return None
    
    data = pd.DataFrame(bars)
    
    if data.empty:
        return None
    
    # Get today's date
    today = datetime.now().date()
    
    # Filter for today's bars only
    data['date'] = pd.to_datetime(data['date'])
    today_data = data[data['date'].dt.date == today]
    
    if today_data.empty:
        write_log(f"No 30-min bars found for today for {contract.symbol}")
        return None
    
    # Get the first bar of the day (9:30-10:00 AM bar)
    first_bar = today_data.iloc[0]
    first_30min_high = first_bar['high']
    
    write_log(f"{contract.symbol} - Today's first 30-min high: {first_30min_high}")
    return first_30min_high


def calculate_daily_atr(ib, contract, period=14):
    """
    Calculate the ATR for daily candlestick data.
    Returns the latest ATR value.
    """
    ib.qualifyContracts(contract)
    
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=f'{period + 5} D',  # Extra days for rolling calculation
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    
    if not bars:
        return None
    
    data = pd.DataFrame(bars)
    
    # Calculate True Range
    data['Prev Close'] = data['close'].shift(1)
    data['TR'] = data.apply(
        lambda row: max(
            row['high'] - row['low'],
            abs(row['high'] - row['Prev Close']) if pd.notna(row['Prev Close']) else row['high'] - row['low'],
            abs(row['low'] - row['Prev Close']) if pd.notna(row['Prev Close']) else row['high'] - row['low']
        ),
        axis=1
    )
    
    # Calculate ATR
    data['ATR'] = data['TR'].rolling(window=period).mean()
    
    atr = data['ATR'].iloc[-1]
    write_log(f"{contract.symbol} - Daily ATR({period}): {atr:.2f}")
    return atr


def calculate_daily_sma(ib, contract, period=10):
    """
    Calculate the daily SMA for trailing stop.
    Returns the latest SMA value.
    """
    ib.qualifyContracts(contract)
    
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=f'{period + 5} D',
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )
    
    if not bars:
        return None
    
    data = pd.DataFrame(bars)
    data['SMA'] = data['close'].rolling(window=period).mean()
    
    sma = data['SMA'].iloc[-1]
    write_log(f"{contract.symbol} - Daily {period}-SMA: {sma:.2f}")
    return sma


def get_current_price(ib, contract):
    """Get the current market price for a contract."""
    ticker_data = ib.reqMktData(contract)
    ib.sleep(2)
    
    price = ticker_data.last if ticker_data.last and not math.isnan(ticker_data.last) else None
    if price is None:
        price = ticker_data.close if ticker_data.close and not math.isnan(ticker_data.close) else None
    
    ib.cancelMktData(contract)
    return price

# ============================================================================
# CALCULATION FUNCTIONS
# ============================================================================
def calculate_quantity(risk_amount, entry_price, stop_loss_price):
    """Calculate position size based on risk amount."""
    risk_per_share = abs(entry_price - stop_loss_price)
    if risk_per_share <= 0:
        raise ValueError("Stop-loss price must be different from the entry price.")
    quantity = risk_amount / risk_per_share
    return math.floor(quantity)


def calculate_trade_levels(entry_price, atr, sma_10):
    """
    Calculate all trade levels based on the strategy rules.
    
    Returns:
        dict: Contains stop_loss, target1, and trailing_stop (10-SMA) prices
    """
    # Stop Loss: 1.5 × ATR below entry
    stop_loss = round(entry_price - (ATR_MULTIPLIER * atr), 2)
    
    # Risk amount per share
    risk_per_share = entry_price - stop_loss
    
    # Target 1: 2 × Risk above entry
    target1 = round(entry_price + (TARGET_RISK_MULTIPLE * risk_per_share), 2)
    
    # Trailing Stop: 10-SMA (for Target 2)
    trailing_stop = round(sma_10, 2)
    
    return {
        'stop_loss': stop_loss,
        'target1': target1,
        'trailing_stop': trailing_stop,
        'risk_per_share': risk_per_share
    }

# ============================================================================
# ORDER FUNCTIONS
# ============================================================================
def create_split_bracket_order(ib, action, total_quantity, stop_loss_price, target1_price, trailing_stop_price):
    """
    Creates a split bracket order:
    - 50% with fixed target (Target 1)
    - 50% with trailing stop at 10-SMA (Target 2)
    
    Returns list of orders to place.
    """
    qty_target1 = total_quantity // 2
    qty_target2 = total_quantity - qty_target1
    
    orders = []
    
    # ========== PART 1: 50% with Target 1 ==========
    if qty_target1 > 0:
        # Parent Order (Market Order) for first half
        parent1 = MarketOrder(action, qty_target1)
        parent1.transmit = False
        parent1.orderId = ib.client.getReqId()
        parent1.tif = 'GTC'
        parent1.outsideRth = True
        
        # Stop-Loss Order for first half
        stop1 = StopOrder('SELL', qty_target1, stop_loss_price)
        stop1.parentId = parent1.orderId
        stop1.transmit = False
        stop1.tif = 'GTC'
        stop1.outsideRth = True
        
        # Take-Profit Order for first half (2x Risk)
        target1 = LimitOrder('SELL', qty_target1, target1_price)
        target1.parentId = parent1.orderId
        target1.transmit = True
        target1.tif = 'GTC'
        target1.outsideRth = True
        
        orders.append(('Target1', [parent1, stop1, target1]))
    
    # ========== PART 2: 50% with Trailing 10-SMA Stop ==========
    if qty_target2 > 0:
        # Parent Order (Market Order) for second half
        parent2 = MarketOrder(action, qty_target2)
        parent2.transmit = False
        parent2.orderId = ib.client.getReqId()
        parent2.tif = 'GTC'
        parent2.outsideRth = True
        
        # Initial Stop-Loss Order for second half (will be updated to trail 10-SMA)
        # Start with the same stop loss, then trail with 10-SMA
        stop2 = StopOrder('SELL', qty_target2, trailing_stop_price)
        stop2.parentId = parent2.orderId
        stop2.transmit = True
        stop2.tif = 'GTC'
        stop2.outsideRth = True
        
        orders.append(('Target2-Trail', [parent2, stop2]))
    
    return orders

# ============================================================================
# MAIN STRATEGY LOGIC
# ============================================================================
def process_ticker(ib, ticker):
    """
    Process a single ticker for breakout entry.
    """
    write_log(f"Processing {ticker}...")
    
    contract = Stock(ticker, 'SMART', 'USD')
    
    try:
        ib.qualifyContracts(contract)
    except Exception as e:
        write_log(f"Failed to qualify contract for {ticker}: {e}")
        return False
    
    # 1. Get today's first 30-min high
    breakout_level = fetch_todays_30min_high(ib, contract)
    if breakout_level is None:
        write_log(f"Could not fetch 30-min high for {ticker}. Skipping.")
        return False
    
    # 2. Get current price
    current_price = get_current_price(ib, contract)
    if current_price is None:
        write_log(f"Could not get current price for {ticker}. Skipping.")
        return False
    
    write_log(f"{ticker} - Current Price: {current_price}, Breakout Level: {breakout_level}")
    
    # 3. Check if price has broken out
    if current_price <= breakout_level:
        write_log(f"{ticker} - No breakout yet. Current: {current_price} <= Breakout: {breakout_level}")
        return False
    
    write_log(f"*** BREAKOUT DETECTED for {ticker}! ***")
    
    # 4. Calculate ATR and 10-SMA
    atr = calculate_daily_atr(ib, contract, ATR_PERIOD)
    if atr is None or math.isnan(atr):
        write_log(f"ATR not available for {ticker}. Skipping.")
        return False
    
    sma_10 = calculate_daily_sma(ib, contract, SMA_PERIOD)
    if sma_10 is None or math.isnan(sma_10):
        write_log(f"10-SMA not available for {ticker}. Skipping.")
        return False
    
    # 5. Calculate trade levels
    entry_price = current_price
    levels = calculate_trade_levels(entry_price, atr, sma_10)
    
    write_log(f"{ticker} Trade Levels:")
    write_log(f"  Entry: {entry_price}")
    write_log(f"  Stop Loss: {levels['stop_loss']} (1.5 x ATR below)")
    write_log(f"  Target 1: {levels['target1']} (2x Risk)")
    write_log(f"  Trailing Stop: {levels['trailing_stop']} (10-SMA)")
    
    # 6. Validate stop loss
    if levels['stop_loss'] >= entry_price:
        write_log(f"Invalid stop loss for {ticker}. Stop: {levels['stop_loss']} >= Entry: {entry_price}")
        return False
    
    # 7. Calculate quantity
    quantity = calculate_quantity(RISK_AMOUNT, entry_price, levels['stop_loss'])
    if quantity <= 0:
        write_log(f"Invalid quantity for {ticker}. Skipping.")
        return False
    
    write_log(f"{ticker} - Quantity: {quantity} shares (${RISK_AMOUNT} risk)")
    
    # 8. Create and place split bracket orders
    order_groups = create_split_bracket_order(
        ib,
        'BUY',
        quantity,
        levels['stop_loss'],
        levels['target1'],
        levels['trailing_stop']
    )
    
    for group_name, orders in order_groups:
        write_log(f"Placing {group_name} orders for {ticker}...")
        for order in orders:
            ib.placeOrder(contract, order)
            ib.sleep(1)
    
    # 9. Log trade
    write_trade(
        ticker,
        entry_price,
        quantity,
        levels['stop_loss'],
        levels['target1'],
        f"Trail 10-SMA: {levels['trailing_stop']}"
    )
    
    write_log(f"=== Orders placed for {ticker} ===")
    return True


def read_tickers_from_file(file_path):
    """Read tickers from a file (comma or newline separated)."""
    with open(file_path, 'r') as file:
        content = file.read().strip()
        tickers = [ticker.strip() for ticker in content.replace(',', '\n').splitlines() if ticker.strip()]
    return tickers


def main():
    """Main entry point for the strategy."""
    print("=" * 60)
    print("30-Minute High Breakout Strategy")
    print("=" * 60)
    write_log("Strategy started")
    
    # Connect to IBKR
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=CLIENT_ID)
        write_log(f"Connected to IBKR at {IBKR_HOST}:{IBKR_PORT}")
    except Exception as e:
        write_log(f"Failed to connect to IBKR: {e}")
        return
    
    try:
        # Get existing positions to avoid duplicates
        positions = ib.positions()
        existing_symbols = {pos.contract.symbol for pos in positions}
        write_log(f"Existing positions: {existing_symbols}")
        
        # Read tickers from finviz-daily3up.csv
        directory = os.path.dirname(__file__)
        ticker_file = os.path.join(directory, 'tickers', 'finviz-daily3up.csv')
        
        if not os.path.exists(ticker_file):
            write_log(f"Ticker file not found: {ticker_file}")
            return
        
        all_tickers = read_tickers_from_file(ticker_file)
        write_log(f"Loaded {len(all_tickers)} tickers from finviz-daily3up.csv")
        
        # Remove duplicates and exclude existing positions
        unique_tickers = list(set(all_tickers) - existing_symbols)
        write_log(f"Processing {len(unique_tickers)} tickers (excluding existing positions)")
        
        # Process each ticker
        trades_placed = 0
        for ticker in unique_tickers:
            try:
                if process_ticker(ib, ticker):
                    trades_placed += 1
                ib.sleep(2)  # Rate limiting
            except Exception as e:
                write_log(f"Error processing {ticker}: {e}")
                continue
        
        write_log(f"Strategy complete. Trades placed: {trades_placed}")
        
    finally:
        write_log("Disconnecting from IBKR")
        ib.disconnect()


if __name__ == '__main__':
    main()
