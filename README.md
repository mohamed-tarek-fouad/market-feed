# market-feed

Binance prices for Claude's 30-minute market read (BTC, ETH, SOL and gold via PAXG), fetched on GitHub's servers so the reads don't need a PC.

- `feed.py` fetches 15m (1000), 1h (500) and 4h (300) candles for BTCUSDT, ETHUSDT, SOLUSDT and PAXGUSDT from Binance's public market-data API. It writes them in the compact format the journal helper reads.
- `.github/workflows/feed.yml` runs `feed.py` and publishes `latest.json` and `status.json` to the `data` branch, replacing the previous copy so the repo stays small. A push to the `request` branch asks for fresh prices immediately; the schedule keeps a recent backup copy.
- `get_prices.py` runs in Claude's scheduled read. It pushes to `request`, waits for the answer on `data`, and hands the prices to the helper. If GitHub doesn't answer in time, it uses the newest copy when it is under 20 minutes old.

Market data only: no keys, no accounts, no orders.
