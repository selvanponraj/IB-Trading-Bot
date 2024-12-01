from pytickersymbols import PyTickerSymbols

stock_data = PyTickerSymbols()
# the naming conversation is get_{index_name}_{exchange_city}_{yahoo or google}_tickers
dax_google = stock_data.get_dax_frankfurt_google_tickers()
dax_yahoo = stock_data.get_dax_frankfurt_yahoo_tickers()
sp100_yahoo = stock_data.get_sp_100_nyc_yahoo_tickers()
sp500_google = stock_data.get_sp_500_nyc_google_tickers()
dow_yahoo = stock_data.get_dow_jones_nyc_yahoo_tickers()
# there are too many combination. Here is a complete list of all getters
all_ticker_getter_names = list(filter(
   lambda x: (
         x.endswith('_google_tickers') or x.endswith('_yahoo_tickers')
   ),
   dir(stock_data),
))
print(all_ticker_getter_names)
print(sp500_google)