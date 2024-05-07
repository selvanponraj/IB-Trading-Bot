import base64
import re
import time
from collections import defaultdict
import pandas as pd
import requests
from ib_insync import CFD
from ib_insync import IB, Future, Forex
from ib_insync import util
import datetime
from datetime import timedelta, datetime, timezone
from order import *
from utils import *
from config import *
import subprocess
import pkg_resources
import csv

# Zavolání funkce na začátku programu
install_requirements()
# Globální seznam pro sledování otevřených obchodů a jejich klouzavých průměrů
open_trades = []


def reconnect(ib_instance):
    if not ib_instance.isConnected():
        print("Connection to IB API lost, trying to connect again...")
        try:
            ib_instance.connect('127.0.0.1', 7497, clientId=1)
            print("The connection to the IB API has been restored.")
        except Exception as e:
           print(f"Error trying to reconnect: {e}")


def connect_to_ib():
    ib = IB()
    max_attempts = 100
    attempt = 0

    while attempt < max_attempts:
        try:
            ib.connect('127.0.0.1', 7497, clientId=1)
            print("\n\n>> Connection to Interactive Brokers was successful.")
            return ib
        except ConnectionRefusedError:
            print("Connection to Interactive Brokers refused. Waiting and retrying...")
            attempt += 1
            time.sleep(30)
        except Exception as e:
            print(f"Connection error: {e}")
            return None

    print("Maximum number of attempts to connect to Interactive Brokers exceeded.")
    return None


# Připojit se k IB
ib = None
if ib is None:
    
    now = datetime.now(timezone.utc)
    print(now)
    day = now.weekday()  # 0 je pondělí, 6 je neděle
    print(day)
    hour = now.hour
    print(hour)
    exit()

# Kontrola, zda jste připojeni k paper trading účtu
if not is_paper_account(ib):
    print("Chyba: Aplikace je určena pouze pro použití s paper trading účtem.")
    exit()

ascii()
# Získání přihlašovacích údajů od uživatele
username = input("Enter your email : ")
password = input("Enter password: ")

# Main Report
print_red("\n\nTo continue, confirm that you have checked the settings (in the config.py file) of moving averages.\n"
          "It's different for ES/MES (large accounts) than CFD (small accounts)!")

while True:
    odpoved = input("Answer (Yes/No): ").lower()
    if odpoved == "yes" or odpoved == "y":
        print("Ok, We continue...\n")
        break
    elif odpoved == "no" or odpoved == "n":
        print("Program ended, check settings.")
        break
    else:
        print_red("Wrong, you have to answer Yes or No")


def select_account(ib_instance):
    # Get account summary
    account_summary = ib_instance.accountSummary()

    # Dictionary for keeping account information
    account_info = {}

    # Processing and storage of account information
    for item in account_summary:
        # If the account has not yet been processed, we add it to the dictionary
        if item.account not in account_info:
            account_info[item.account] = {'TotalCashValue': 'Unknown', 'Currency': 'Unknown'}

        # Update account information
        if item.tag == 'TotalCashValue':
            account_info[item.account]['TotalCashValue'] = item.value
            account_info[item.account][
                'Currency'] = item.currency # We assume that the currency is provided in the 'currency' argument

    # List of available business accounts and their status
    print("List of trading accounts and their status:")
    for account, info in account_info.items():
        print(f"Account: {account}, Account Status: {info['TotalCashValue']}, Currency: {info['Currency']}")

    # Let the user select an account
    account_number = input("Enter the number of the account to be traded on: ")

    # Save the account number in the configuration
    config['account_number'] = account_number


# Select a business account
select_account(ib)

print("Account number", config['account_number'])


def convert_to_usd(ib, amount, currency):
    if currency == 'USD':
        return amount

    # Vytvoření objektu měnového páru
    forex_pair = Forex('EURUSD')

    # Získání aktuálního času ve správném formátu pro endDateTime
    end_time = datetime.now().strftime("%Y%m%d %H:%M:%S")
    duration = '3600 S'  # Doba 1 hodina v sekundách
    bars = ib.reqHistoricalData(forex_pair, endDateTime=end_time, durationStr=duration,
                                barSizeSetting='1 hour', whatToShow='MIDPOINT', useRTH=True)

    # Získání poslední svíčky a její uzavírací ceny
    if bars:
        last_candle = bars[-1]
        close_price = last_candle.close
        # print(f'Uzavírací cena poslední 1h svíčky pro {forex_pair}: {close_price}')

        # Přepočítání částky
        converted_amount = amount / close_price
        print(f"Converted account size to $ before leverage: \033[31m{converted_amount:.2f}\033[0m USD")
        return converted_amount
    else:
        print(f"No candles found for {forex_pair} and cannot be recalculated")
        return None


def is_trading_time():
    now = datetime.now(timezone.utc)
    print(now)
    day = now.weekday()  # 0 je pondělí, 6 je neděle
    hour = now.hour
    # Checking if the time is in business hours (Monday 8:00 UTC to Friday 20:00 UTC)
    if 0 <= day <= 4 and 1 <= hour < 21:
        print("Markets are open for trading moodix sentiment")
        return True
    else:
        print("Markets are closed.")
        return False



def get_current_date_string():
    current_date = datetime.now()
    return current_date.strftime('%Y%m%d-23:00:00')


def get_market_sentiment(username, password):
    # Vytvoření Basic Auth řetězce
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()

    print("Získávání informací o sentimentu trhu...")
    url = "https://app.moodix.market/api/moodix-stat/"
    payload = {}
    headers = {
        'Authorization': f'Basic {credentials}'
    }
    try:
        response = requests.request("GET", url, headers=headers, data=payload)
        data = response.json()

        # Extrahujeme sentiment a trend z dat
        sentiment = data['results'][0]['sentiment']
        trend = data['results'][0]['trend']

        return sentiment, trend

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to moodix. Bad username/password or unavailable service: {e}")
        return None


def get_sentiment_check(username, password):
    url = 'https://app.moodix.market/api/algo-stat/1'
    response = requests.get(url, auth=(username, password))
    if response.status_code == 200:
        data = response.json()
        return data.get('sentiment_check', False)
    else:
        print("Error while fetching sentiment: ", response.status_code)
        return False


def calculate_trading_parameters(ib):
    # Získání čísla účtu z konfigurace
    account_number = config.get("account_number", None)

    if not account_number:
        print("The account number is not set in the configuration.")
        return None

    # Získání informací o účtu pro konkrétní číslo účtu
    account_info = ib.accountSummary(account_number)
    account_size = None
    account_currency = None

    for item in account_info:
        if item.tag == 'TotalCashValue':
            print(f"Account size: {item.value} {item.currency}")
            account_size = float(item.value)
            account_currency = item.currency
        elif item.tag == 'MaintMarginReq':
            print(f"Used margin: {item.value} {item.currency}")

    # Kontrola měny a přepočet na USD, pokud je to potřeba
    if account_currency and account_currency != 'USD':
        account_size = convert_to_usd(ib, account_size, account_currency)
        print(f"Account size after conversion to USD: {account_size:.2f} USD")

        # Požádáme uživatele o možnou novou hodnotu
        new_value = input(
            "\n\n\033[31mEnter a new value\033[0m for account size (before leverage) in USD. \nApplies if "
            "do not want to count the full size of the demo account in moodix trading \n\nPress Enter for "
            "continue with original value: ")
        if new_value:
            try:
                account_size = float(new_value)
            except ValueError:
                print("Invalid value, original value is used.")

    if account_size is not None:
        sorted_account_sizes = sorted(config['size_account'].keys(), reverse=True)

        # Najděte nejbližší nižší nebo rovnou hodnotu k velikosti účtu
        selected_account_size = None
        for size in sorted_account_sizes:
            if account_size >= size:
                selected_account_size = size
                break

        # Převod slovníku na DataFrame
        df = pd.json_normalize(config, sep='_')

        # Uložení config do CSV souboru
        df.to_csv('config.csv', index=False)

        if selected_account_size is not None:
            instrument_type = config['size_account'][selected_account_size]['type']
            print(f"\n\nInstrument type will be used for trading: \033[31m{instrument_type}\033[0m")

            # Vypočítáme velikost účtu po páce
            leverage = config['leverage']
            leveraged_account_size = account_size * leverage
            config['leveraged_size_account'] = leveraged_account_size
            print(f"Account size after leveraging: \033[31m{leveraged_account_size:.2f}\033[0m USD")

            # Získáme multiplikátor kontraktu
            long_contract = config['size_account'][selected_account_size]['long_contract']
            if instrument_type == 'SPY':
                contract_size = 4000.0
            else:
                contract_size = float(long_contract.multiplier) * 4000

            # Uložení config do CSV souboru
            df.to_csv('config.csv', index=False)

            # Let's calculate, kolik Contracts můžeme mít otevřeno najednou
            total_contracts = round(leveraged_account_size / contract_size)

            # Vypočítáme, kolik kontraktů můžeme mít na jeden obchod
            max_positions = config['max_positions']
            contracts_per_trade = round(total_contracts / max_positions)
            if contracts_per_trade == 0:
                contracts_per_trade = 1

            config['contracts_per_trade'] = contracts_per_trade
            print(
                f"For trading with \033[31m{instrument_type}\033[0m we can have a total of \033[31m{total_contracts:.2f}\033[0m contracts open for the entire account.")
            print(
                f"For trading \033[31m{instrument_type}\033[0m we can have open \033[31m{contracts_per_trade:.2f}\033[0m contracts per trade.")
            # Čekáme na uživatele, aby stiskl Enter
            input("Press Enter to continue...")
            return selected_account_size
        else:
            print("The account is too small, cannot determine the instrument type.")
            return None
    else:
        print("Failed to get account size information.")
        return None


def contracts_spec():
    for account_size, details in config['size_account'].items():
        contract_type = details['type']
        if contract_type == 'SPY':
            spy_contract = CFD('IBUS500', 'smart', 'USD')
            config['size_account'][account_size]['long_contract'] = spy_contract
        elif contract_type in ['MES', 'ES']:
            # Pro futures MES a ES najdeme nejbližší dostupný kontrakt
            contract = Future(contract_type, exchange='CME')
            contracts = ib.reqContractDetails(contract)
            print(contract)
            if contracts:
                nearest_contract = min(contracts, key=lambda x: x.contract.lastTradeDateOrContractMonth)
                config['size_account'][account_size]['long_contract'] = nearest_contract.contract
            else:
                print(f"No contract found for {contract_type}")


def next_contracts_spec():
    for account_size, details in config['size_account'].items():
        contract_type = details['type']
        long_contract = details.get('long_contract')

        if contract_type == 'SPY':
            spy_contract = CFD('IBUS500', 'smart', 'USD')
            config['size_account'][account_size]['short_contract'] = spy_contract
        elif contract_type in ['MES', 'ES']:
            contract = Future(contract_type, exchange='CME')
            contracts = ib.reqContractDetails(contract)

            if contracts:
                now = datetime.now()
                future_contracts = [c for c in contracts if
                                    datetime.strptime(c.contract.lastTradeDateOrContractMonth, "%Y%m%d") > now]

                if future_contracts:
                    # Odstraňte kontrakt, který je již nastaven jako long_contract
                    if long_contract:
                        future_contracts = [c for c in future_contracts if c.contract != long_contract]

                    if future_contracts:
                        next_contract = min(future_contracts, key=lambda x: x.contract.lastTradeDateOrContractMonth)
                        config['size_account'][account_size]['short_contract'] = next_contract.contract
                    else:
                        print(f"No other future contract found for {contract_type}")
                else:
                    print(f"No future contract found for {contract_type}")
            else:
                print(f"No contract found for {contract_type}")


def display_grouped_orders(grouped_orders):
    print("------------------------------------------------------------------------")
    for parent_id, orders in grouped_orders.items():
        print(f"Business group for main order {parent_id}:")
        for trade in orders:
            contract = trade.contract
            order = trade.order
            order_status = trade.orderStatus
            print(
                f"{contract.symbol} > {contract.secType} {order.orderRef}> {order.action} > {order.orderType} > {order_status.status} > {order.totalQuantity} > {order.totalQuantity}")
        print()


def cancel_bracket_orders(grouped_orders):
    for parent_id, orders in grouped_orders.items():
        for trade in orders:
            # Získání ID objednávky
            order_id = trade.order.orderId

            # Zrušení objednávky
            ib.cancelOrder(order_id)
            print(f"Order with ID {order_id} has been cancelled.")


def group_orders_by_parent(open_trades):
    grouped_orders = defaultdict(list)
    for trade in open_trades:
        parent_id = trade.order.parentId
        if parent_id == 0:
            parent_id = trade.order.orderId
        grouped_orders[parent_id].append(trade)
    return grouped_orders


def display_and_check_open_trades(config, open_trades):
    grouped_orders = group_orders_by_parent(open_trades)
    #print(grouped_orders)
    opened_mas = defaultdict(list)

    for parent_id, orders in grouped_orders.items():
        for trade in orders:
            contract = trade.contract
            order = trade.order
            order_status = trade.orderStatus

            # Získání klouzavého průměru z referencí objednávek
            ma = extract_moving_average_from_order_ref(order.orderRef)
            if ma is not None:
                opened_mas[ma].append(trade)

                # Zobrazení informací o obchodu
                # print(
                #     f"Hlavní objednávka (id {parent_id}) > Klouzavý průměr {ma} > Směr {order.action} > Status {order_status.status}")

    # Kontrola, zda pro každý klouzavý průměr již existuje otevřená objednávka
    mas_without_orders = []

    for ma in config['ma_configurations'].keys():
        if ma in opened_mas:
            if any(trade.orderStatus.status in ['Submitted', 'Presubmitted', 'Inactive', 'PendingCancel'] for trade in opened_mas[ma]):
                print(f"There are already open trades for moving average {ma}.")
                continue
        print(f"There are no open trades for moving average {ma}.")
        mas_without_orders.append(ma)

    return mas_without_orders, opened_mas


def extract_moving_average_from_order_ref(order_ref):
    if order_ref is not None and isinstance(order_ref, str):
        ma_match = re.search(r'(\d+)', order_ref)
        if ma_match:
            return int(ma_match.group(1))
    return None


def get_moving_averages(instrument, duration, end_date):
    print("------------------------------------------------------------------------")
    print(f"Getting moving averages for {instrument}...")
    contract = get_contract_for_instrument(instrument)

    print(f"Contract to get moving averages: {contract.localSymbol}")
    print(f"History length: {duration}")
    print(f"End date and time: {end_date}")
    print(f"Candle size: 10 mins")
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting='10 mins',
            whatToShow='MIDPOINT',
            useRTH=False
        )
        if not bars:
            print("Failed to get historical data.")
            return None

        df = util.df(bars)

        ma_values = {}
        for ma_period in config['ma_configurations'].keys():
            ma_column_name = f'{ma_period}'
            df[ma_column_name] = df['close'].rolling(window=ma_period).mean()
            ma_values[ma_period] = df[ma_column_name].iloc[-1]
            print(f"Moving average {ma_period}: {ma_values[ma_period]}")

        return ma_values
    except Exception as e:
        print(f"Error loading historical data: {e}")
        return None


def place_limit_order(action, instrument_type, ma_period, ma_value, ma_config, opened_mas, next_ma):
    print("------------------------------------------------------------------------")
    if ma_period in opened_mas and opened_mas[ma_period]:
        print(f"There is already an open order for moving average {ma_period}. A new order will not be placed.")
        return
    print(f"Creating {action} limit order for {instrument_type} with moving average {ma_period}...")
    contract = get_contract_for_instrument(instrument_type)

    # Získejte aktuální cenu nástroje
    ticker = ib.reqMktData(contract)
    ib.sleep(1)  # Počkejte chvíli, aby se data aktualizoval
    current_price = ticker.marketPrice()
    print("Cena ", current_price, "MA ", ma_value)

    # Kontrola ceny vzhledem k akci a klouzavému průměru
    min_difference_percentage = config['min_difference']
    min_difference = ma_value * (min_difference_percentage / 100)
    if action == 'BUY' and (current_price - ma_value) < min_difference:
        print("The current price is too close or below the moving average, the order will not be sent.")
        return
    elif action == 'SELL' and (ma_value - current_price) < min_difference:
        print("The current price is too close or above the moving average, the order will not be sent.")
        return

    # kontrola pro největší průměr
    if action == 'BUY' and ma_period == config['max_ma']:
        next_ma -= 30
    elif action == 'SELL' and ma_period == config['max_ma']:
        next_ma += 30

    print("MA: ", (ma_value - config['ma_configurations'][ma_period]['distance']), "next ma: ", next_ma)

    if action == 'BUY' and (ma_value -config['ma_configurations'][ma_period]['distance']) < next_ma:
        print(
            "The current moving average price is too close to the next moving average, the order will not be sent.")
        return
    elif action == 'SELL' and (ma_value + config['ma_configurations'][ma_period]['distance']) > next_ma:
        print("The current moving average price is too close to the next moving average, the order will not be sent.")
        return

    ma_value = round_to_quarter(ma_value)

    if action == 'BUY':
        stop_loss_price = round_to_quarter(ma_value * (1 - ma_config['stop_loss']))
        take_profit_price = round_to_quarter(ma_value * (1 + ma_config['take_profit']))
    else:  # SELL
        stop_loss_price = round_to_quarter(ma_value * (1 + ma_config['stop_loss']))
        take_profit_price = round_to_quarter(ma_value * (1 - ma_config['take_profit']))

    # Nastavte, jak dlouho má být objednávka platná (například 1 hodina)
    expiration_time = datetime.now() + timedelta(minutes=15)

    # Formátujte datum a čas pro IB API
    expiration_time_str = expiration_time.strftime("%Y%m%d %H:%M:%S")

    bracket_order = ib.bracketOrder(
        action=action,
        quantity=config['contracts_per_trade'],
        limitPrice=ma_value,
        takeProfitPrice=take_profit_price,
        stopLossPrice=stop_loss_price,
        outsideRth=True,
        orderRef=f"{ma_period}",
        tif='GTC'
    )

    # Nastavení GTD a expiračního času pouze pro hlavní objednávku
    bracket_order.parent.tif = 'GTD'
    bracket_order.parent.goodTillDate = expiration_time_str

    bracket_order.parent.orderRef = f"{ma_period}"

    # # Nastavení subúčtu pro každou objednávku v bracketu
    bracket_order.parent.account = config['account_number']  # Nastavení subúčtu pro parent objednávku
    bracket_order.takeProfit.account = config['account_number']  # Nastavení subúčtu pro takeProfit objednávku
    bracket_order.stopLoss.account = config['account_number']  # Nastavení subúčtu pro stopLoss objednávku

    main_trade = ib.placeOrder(contract, bracket_order.parent)
    ib.placeOrder(contract, bracket_order.takeProfit)
    ib.placeOrder(contract, bracket_order.stopLoss)

    for _ in range(10):
        ib.sleep(1)
        if main_trade.orderStatus.status in ['Submitted', 'Filled']:
            break

    if main_trade.orderStatus.status in ['Submitted', 'Filled', 'PendingSubmit']:
        print(f"Trade {action} na {instrument_type} with a moving average {ma_period} was opened.")
        return main_trade
    else:
        print(f"Trade {action} na {instrument_type} with a moving average {ma_period} was not opened.")
        return None


def should_open_long(sentiment, trend):
    return (
            (sentiment == 'RiskOn' and trend in ['Growing', 'Sideways']) or
            (sentiment == 'RiskOff' and trend in ['Fading'])
    )


def should_open_short(sentiment, trend):
    return sentiment == 'RiskOff' and trend == 'Growing'


def is_long_trades_enabled():
    return config['long_trades']


def is_short_trades_enabled():
    return config['short_trades']


def round_to_quarter(value):
    return round(value * 4) / 4


def get_contract_for_instrument(instrument):
    if instrument == 'SPY':
        # return Stock('SPY', 'ARCA')
        return CFD('IBUS500', 'smart', 'USD')
    elif instrument in ['MES', 'ES']:
        generic_contract = Future(instrument, exchange='CME')
        contracts = ib.reqContractDetails(generic_contract)

        if not contracts:
            raise ValueError(f"Could not find contract for {instrument} na CME.")

        sorted_contracts = sorted(contracts, key=lambda x: x.contract.lastTradeDateOrContractMonth)
        return sorted_contracts[0].contract
    else:
        raise ValueError(f"Unknown instrument: {instrument}")


# nastaveni uctu
print("Trading account setup ...")
contracts_spec()
next_contracts_spec()
selected_account_size = calculate_trading_parameters(ib)

# Hlavní smyčka
print("I start the main loop...")
while True:
    if is_trading_time():
        # sentiment_state = get_sentiment_check(username, password)
        sentiment_state = True
        if sentiment_state:
            print("Checking systems: ", "\033[92m OK \033[0m")
            try:
                # Zkontrolovat a obnovit připojení před každou operací, která vyžaduje komunikaci s IB API
                reconnect(ib)
                # moodix sentiment
                # sentiment, trend = get_market_sentiment(username, password)
                sentiment, trend = ("RiskOn","Growing")
                print("------------------------------------------------------------------------")
                print(f"Current sentiment: {sentiment}, trend: {trend}")
                if sentiment is None:
                    print("Failed to load sentiment. I'm waiting for another try.")
                    time.sleep(60)
                    continue
                print("------------------------------------------------------------------------")
                # # nastaveni uct
                # contracts_spec()
                # next_contracts_spec()
                # selected_account_size = calculate_trading_parameters(ib)

                # Získání informací o otevřených obchodech
                open_trades = ib.openTrades()
                grouped_orders = group_orders_by_parent(open_trades)
                display_grouped_orders(grouped_orders)

                # Zobrazení a kontrola otevřených obchodů
                mas_without_orders, opened_mas = display_and_check_open_trades(config, open_trades)

                # Kontrola, zda byl vybrán typ účtu
                if selected_account_size is None:
                    print("Error: Account size is too small or failed to get account information.")
                    time.sleep(60)
                    continue

                # Získání hodnot klouzavých průměrů
                instrument_type = config['size_account'][selected_account_size]['type']
                ma_values = get_moving_averages(instrument_type, '10 D', get_current_date_string())

                # Položení objednávek pro klouzavé průměry bez otevřených pozic
                for ma in mas_without_orders:
                    # print(mas_without_orders)
                    # ma_value = ma_values[f'MA{ma}'].iloc[-1]
                    ma_config = config['ma_configurations'][ma]
                    # print(ma_config)
                    ma_value = ma_values[ma]
                    next_ma = config['ma_configurations'][ma]['next']
                    next_ma_value = ma_values[next_ma]
                    # print(next_ma_value)

                    if should_open_long(sentiment, trend):
                        if is_long_trades_enabled:
                            place_limit_order('BUY', instrument_type, ma, ma_value, ma_config, opened_mas, next_ma_value)
                        else:
                            print("Long trades not allowed")
                            break
                    elif should_open_short(sentiment, trend):
                        if is_short_trades_enabled():
                            place_limit_order('SELL', instrument_type, ma, ma_value, ma_config, opened_mas, next_ma_value)
                        else:
                            print("Short trades not allowed")
                            break

                # opened_mas = []
                # mas_without_orders = []
                # Počkejte 5 sekund před dalším během smyčky
                print("I wait 5 seconds before the next cycle...")
                time.sleep(5)
            except Exception as e:
                print(f"Error communicating with broker on API: {e}")
                reconnect(ib)  # Pokus o opětovné připojení, pokud došlo k chybě
                time.sleep(60)
            pass
        else:
            print("Systems check:", "\033[31m Suspended \033[0m")
            print("Suspended for 5 minutes by moodix due to expectation of macro event or other reason")
            # Získání informací o otevřených obchodech
            # open_trades = ib.openTrades()
            # grouped_orders = group_orders_by_parent(open_trades)
            # cancel_bracket_orders(grouped_orders)
            time.sleep(300)  # Pauza na 60 sekund
    else:

        print("I wait 5 min. ...")
        time.sleep(360)

