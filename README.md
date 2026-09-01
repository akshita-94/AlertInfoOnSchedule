# AlertingData

Stateless phone alerts for:

- Gold India 22K price per gram
- USD to INR conversion rate
- GOOGL price
- MRNA price
- FXAIX price

The project has no database and no always-on server. GitHub Actions runs the script on a schedule and Telegram delivers the phone notification.

## Schedule

Configured for Seattle time:

- 7:30 AM America/Los_Angeles
- 12:00 PM America/Los_Angeles
- 10:45 PM America/Los_Angeles

## Free Data Sources

- Gold: `https://api.goldprice.dev/v1/carat?currency=INR`
- USD/INR: `https://api.frankfurter.dev/v2/rate/USD/INR?providers=FBIL`
- Market quotes: Yahoo Finance public chart endpoint by default

The Yahoo Finance endpoint is the easiest no-key option for personal use, but it is not an official market-data API. To use Alpha Vantage instead, set `MARKET_DATA_PROVIDER=alpha_vantage` and add an `ALPHA_VANTAGE_API_KEY` secret. Alpha Vantage's free tier is currently enough for this project because it needs 9 market quote calls per day.

## GitHub Secrets

In your GitHub repository, go to:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Create these secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional:

- `ALPHA_VANTAGE_API_KEY`

If you pasted your Telegram token in any chat, revoke it in BotFather and generate a new one before saving it in GitHub.

## Local Test

Create a local `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_new_bot_token
TELEGRAM_CHAT_ID=your_chat_id
ALERT_TIMEZONE=America/Los_Angeles
MARKET_DATA_PROVIDER=yahoo
```

Preview the alert without sending:

```bash
python3 alert.py --dry-run
```

Send a real Telegram alert:

```bash
python3 alert.py
```

## Expected Alert

```text
Morning Alert
Aug 31, 2026 7:30 AM PDT

Gold India 22K: ₹12,345.67/g
USD/INR: 83.1234
GOOGL: $200.12
MRNA: $31.45
FXAIX: $215.67
```
