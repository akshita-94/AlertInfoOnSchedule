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

GitHub Actions runs scheduled workflows from UTC cron entries. This workflow uses candidate UTC times for both PDT and PST, and `alert.py` checks Seattle local time before sending so daylight saving changes do not create duplicate alerts.

## Free Data Sources

- Gold: Groww India gold-rate page by default
- USD/INR: `https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR`
- Market quotes: Yahoo Finance public chart endpoint by default

The Groww page is used because it is closer to the retail-style "gold rate in India" most people expect. The cleaner gold API, `goldprice.dev`, returns spot metal value by purity and does not include India retail jewellery premiums, so it can look low compared with Indian gold-rate sites. To use that spot value instead, set `GOLD_DATA_PROVIDER=spot`.

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
GOLD_DATA_PROVIDER=groww
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

Gold India 22K: ₹14,370.00/g
USD/INR: 95.1700
GOOGL: $339.35
MRNA: $140.34
FXAIX: $267.46
```
