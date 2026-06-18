# Telegram Mini App + Stars deployment

This project serves the Telegram Mini App from the same FastAPI process as the
admin UI:

- Mini App frontend: `GET /`
- Static assets: `GET /miniapp-static/*`
- Telegram initData validation: `POST /api/telegram/validate-init-data`
- Stars invoice link creation: `POST /api/payments/stars/invoice-link`
- Admin UI remains under `GET /admin/*`
- Telegram bot remains long polling; do not expose a webhook.

## Environment

Set these on the Coolify app:

```bash
telegram_token=<BotFather token>
admin_host=0.0.0.0
admin_port=3000
mini_app_allowed_origins=https://mini.example.com
mini_app_init_data_max_age_seconds=86400
```

Use the real public Mini App origin for `mini_app_allowed_origins`. During local
development, `*` is acceptable.

## Cloudflare Tunnel

Cloudflare Tunnel should run on the Coolify Linux box and publish only the web
surface. The bot keeps long polling from the private host.

Dashboard-managed tunnel:

1. Cloudflare Zero Trust -> Networks -> Connectors -> Cloudflare Tunnels.
2. Create a Cloudflared tunnel and run the generated connector command on the
   Coolify box.
3. Add a published application route:
   - Public hostname: `mini.example.com`
   - Service URL: `http://localhost:3000` or the Coolify internal app URL/port.

Locally-managed tunnel equivalent:

```bash
cloudflared tunnel create videogirl-miniapp
cloudflared tunnel route dns videogirl-miniapp mini.example.com
cloudflared tunnel run videogirl-miniapp
```

The tunnel DNS route can exist while the tunnel is stopped, but users will not
reach the app until `cloudflared` is running.

## BotFather

1. Create or select the bot in `@BotFather`.
2. Use the Mini App/Web App settings to set the public HTTPS URL:
   `https://mini.example.com/`.
3. Keep all public Mini App text SFW. Adult content remains opt-in only inside
   the bot after 18+ verification.

## Stars flow

1. Mini App sends Telegram `initData` to the backend.
2. Backend validates `initData` with HMAC using `telegram_token`.
3. Backend creates a Telegram Stars invoice link with:
   - `currency="XTR"`
   - `provider_token=""`
4. Frontend opens Telegram's native invoice UI.
5. Bot receives `pre_checkout_query`, validates payload/user/currency/amount,
   and answers within Telegram's required checkout window.
6. Bot receives `successful_payment`, stores
   `telegram_payment_charge_id`, and delivers idempotently.

Refunds are available through the service layer via Telegram's
`refundStarPayment` API.
