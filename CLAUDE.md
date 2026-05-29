# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Collect Terminal** — a Django-based collectibles portfolio tracker. Users can search for items on eBay and the Pokémon TCG API, add them to a personal inventory, and view portfolio analytics (P&L, ROI, Sharpe ratio, drawdown, etc.).

## Setup & Running

```bash
# 1. Create and activate a virtual environment (first time)
python3 -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install django requests python-dotenv

# 3. Create .env in the project root
# EBAY_CLIENT_ID=<your production client id>
# EBAY_CLIENT_SECRET=<your production client secret>

# 4. Apply migrations
python manage.py migrate

# 5. Run development server
python manage.py runserver
# Visit http://localhost:8000
```

To create a superuser for the Django admin:
```bash
python manage.py createsuperuser
```

Run tests:
```bash
python manage.py test tracker
```

## Architecture

The project is a single Django app (`tracker`) inside the `dbms_final_project` configuration package.

### Data model (`tracker/models.py`)

Three tables (using explicit `db_table` names for raw SQL clarity):

| Model | Table | Purpose |
|---|---|---|
| `Collectible` | `products` | Master catalog of items sourced from eBay or PTCG API |
| `UserCollection` | `user_inventories` | Per-user holdings (quantity, purchase price, date) |
| `Market_Price` | `price_histories` | Append-only price snapshots per product |

### Views & URL mapping (`tracker/views.py`, `tracker/urls.py`)

All views use **raw SQL via `connection.cursor()`** instead of the Django ORM — this is intentional (DBMS course project). Key views:

| URL | View | Notes |
|---|---|---|
| `/` | `index` | Dashboard with portfolio summary, top gainers/losers |
| `/inventory/` | `inventory_view` | Full holdings list |
| `/search/` | `search_product` | Calls eBay + optional PTCG API |
| `/add/` | `add_to_inventory` | GET = confirm form, POST = insert to DB |
| `/inventory/<id>/edit/` | `edit_inventory` | Consolidates duplicate rows on save (delete-then-insert) |
| `/update-prices/` | `update_prices` | POST triggers live price refresh for all owned items |
| `/roi/` | `roi_dashboard` | ROI per item |
| `/analytics/` | `analytics_dashboard` | Time-series charts, Sharpe/Sortino/Calmar ratios, drawdown |
| `/market/` | `market_dashboard` | Market-wide ranking + category heatmap + PTCG news |
| `/market/refresh-news/` | `refresh_news` | AJAX POST endpoint |
| `/register/` | `register` | Registration using Django's `UserCreationForm` |
| `/accounts/` | Django auth | Login/logout via `django.contrib.auth.urls` |

### External services (`tracker/services.py`)

- **eBay Browse API** (`search_ebay_items`, `get_ebay_average_price`): uses OAuth2 client-credentials flow. Credentials come from `settings.EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` loaded from `.env`. Production endpoint — not sandbox.
- **Pokémon TCG API** (`search_ptcg_cards`, `get_ptcg_card_price`): public API at `api.pokemontcg.io/v2`, no key required for basic usage. Price priority: TCGPlayer market → Cardmarket averageSellPrice.
- **Google News RSS** (`fetch_ptcg_news`): fetches PTCG-related headlines; parsed with stdlib `xml.etree.ElementTree`.

### Templates

All templates extend `tracker/templates/tracker/base.html`. Charts are rendered client-side with Chart.js (CDN). No frontend build step required.

### Database

SQLite (`db.sqlite3`) in the project root. Django's built-in auth tables coexist with the three custom tables above.

## Key Patterns

- **Raw SQL everywhere in views**: when editing queries, use SQLite syntax (e.g., `datetime('now')`, `date('now')`, `INSERT OR IGNORE`).
- **`edit_inventory` delete-then-insert**: updating an item wipes all rows for that `(user_id, product_id)` pair and inserts one consolidated row — this is intentional to handle cases where multiple purchase rows exist.
- **Price history is append-only**: `update_prices` always inserts new rows; it never updates existing ones. Dashboard queries use `ORDER BY recorded_at DESC LIMIT 1` to get the latest price.
