from ib_insync import IB

# Connect to IBKR TWS or IB Gateway
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # Default TWS paper trading port is 7497

# Fetch all open orders
open_orders = ib.openOrders()

if open_orders:
    print(f"Found {len(open_orders)} open order(s). Canceling them now...")
    for order in open_orders:
        ib.cancelOrder(order)
        print(f"Canceled order: {order}")
else:
    print("No open orders found.")

# Disconnect from IBKR
ib.disconnect()