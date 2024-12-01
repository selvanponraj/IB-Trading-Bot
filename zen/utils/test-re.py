import re
import ast

# Sample input string
input_string = "zen-trendingnow.csv : ['COIN', 'FDX', 'MARA', 'TJ']"



# Regular expression
regex = re.compile(r'zen-trendingnow\.csv : \[(.*?)\]')
# Update the regular expression to include 'ze-pullback' and 'zen-readytotrend'
regex = re.compile(r'(zen-trendingnow|zen-pullback|zen-readytotrend)\.csv : \[(.*?)\]')

# Search for the pattern
match = regex.search(input_string)

if match:
    # Extract the matched symbols
    symbols = match.group(1)  # This will get the string inside the brackets
    print(f"Matched symbols string: {symbols}")

    # Convert to a list
    symbols_list = ast.literal_eval(symbols)
    print(f"Symbols list: {symbols_list}")
else:
    print("No match found.")