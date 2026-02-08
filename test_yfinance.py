import yfinance as yf

ticker = yf.Ticker("AAPL")

print("Available expirations:")
print(ticker.options)

chain = ticker.option_chain(ticker.options[0])

print("\nCalls head:")
print(chain.calls.head())

print("\nPuts head:")
print(chain.puts.head())
