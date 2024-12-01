from ib_insync import IB, MarketOrder

# Connect to IBKR TWS or IB Gateway
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # Default TWS paper trading port is 7497

# Fetch all open positions
positions = ib.positions()

if not positions:
    print("No positions found.")
else:
    print(f"Found {len(positions)} position(s). Processing to close...")

    for pos in positions:
        contract = pos.contract
        position_size = pos.position
        
        # Ensure the contract is routed through SMART
        contract.exchange = 'SMART'

        # Determine the required action
        if position_size > 0:
            action = 'SELL'  # Long position, close by selling
        elif position_size < 0:
            action = 'BUY'  # Short position, close by buying
        else:
            print(f"No action needed for {contract.symbol}.")
            continue

        # Check for existing open orders
        open_orders = ib.openTrades()  # Fetch open orders
        open_order_symbols = [
            trade.contract.symbol for trade in open_orders if trade.order.action == action
        ]

        # Skip if there's already an open order with the same action for this symbol
        if contract.symbol in open_order_symbols:
            print(f"Skipping {contract.symbol}, already has an open {action} order.")
            continue

        # Place a market order to close the position
        order = MarketOrder(action, abs(position_size))
        trade = ib.placeOrder(contract, order)

        print(f"Closing position: {action} {abs(position_size)} {contract.symbol} via SMART exchange")
        # Wait briefly to ensure processing
        ib.sleep(1)

# Disconnect from IBKR
ib.disconnect()
print("All positions have been processed.")