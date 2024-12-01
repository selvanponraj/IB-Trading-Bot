import re
import os
from datetime import datetime
from ib_insync import IB, Stock, MarketOrder, StopOrder, LimitOrder
import pandas as pd
import math
import os
import logging

from datetime import datetime, timedelta

import csv

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1) 

log_file_path = f"zen-{datetime.now().strftime('%Y-%m-%d')}.log"
# Function to write log entries
log_directory = os.path.join(os.path.dirname(__file__), 'log')
os.makedirs(log_directory, exist_ok=True)
log_file_path = os.path.join(log_directory, f"zen-{datetime.now().strftime('%Y-%m-%d')}.log")

# Read log data from the file
with open(log_file_path, 'r') as file:
    log_data = file.read()

# Regular expression to capture timestamp, file name, and stock symbols
regex = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.*?) : (\[.*?\]) @ (\d{4}-\d{2}-\d{2} \d{2}:\d{2})')

# Find all matches in the log data
matches = regex.findall(log_data)

# Initialize sets for each file
pullback_set = set()
readytotrend_set = set()
trendingnow_set = set()

# Process matches and add symbols to respective sets
for match in matches:
    filename, symbols_str = match[1], match[2]
    
    # Convert string to list safely if not empty
    symbols = eval(symbols_str) if symbols_str != '[]' else []
    
    if 'zen-pullback.csv' in filename:
        pullback_set.update(symbols)
    elif 'zen-readytotrend.csv' in filename:
        readytotrend_set.update(symbols)
    elif 'zen-trendingnow.csv' in filename:
        trendingnow_set.update(symbols)

# Print the sets
print("zen-pullback.csv symbols:", pullback_set)
print("zen-readytotrend.csv symbols:", readytotrend_set)
print("zen-trendingnow.csv symbols:", trendingnow_set)
