# osu!insights

A web-based analytics platform for osu! Standard players. Players can search any username to view their performance stats, compare against their rank tier average, and get personalised improvement suggestions. The system ingests data from the osu! API v2 and stores it in a PostgreSQL database.

---

## Requirements

- Python 3.12+
- PostgreSQL 18
- pip packages: `flask`, `psycopg2-binary`, `pandas`, `matplotlib`, `python-dotenv`

Install dependencies:

```
pip install flask psycopg2-binary pandas matplotlib python-dotenv
```

---

## Setup

**1. Create a `.env` file in the project root:**

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=osuanalytics
DB_USER=postgres
DB_PASSWORD=your_password

OSU_CLIENT_ID=your_client_id
OSU_CLIENT_SECRET=your_client_secret
```

**2. Run the SQL files in order to set up the database:**

```
psql -U postgres -d osuanalytics -f sql/01_schema.sql
psql -U postgres -d osuanalytics -f sql/02_queries.sql
psql -U postgres -d osuanalytics -f sql/03_views.sql
psql -U postgres -d osuanalytics -f sql/04_procedures.sql
```

**3. Run the bulk ingest to populate player data:**

```
python etl/bulk_ingest.py
```

This fetches the top 10,000 globally ranked osu! players from the osu! API.

---

## Running the App

```
python app/flask_app.py
```

Then open `http://localhost:5000` in a browser.

---

## Project Structure

```
database/
├── app/
│   ├── flask_app.py        # Flask routes and API endpoints
│   ├── db.py               # Database connection and query helpers
│   ├── templates/          # Jinja2 HTML templates
│   └── static/             # CSS, JS, and image assets
├── etl/
│   ├── osu_api.py          # osu! API v2 OAuth2 client
│   ├── bulk_ingest.py      # Bulk player ingestion from ranking pages
│   ├── ingest_players.py   # Individual player + score ingestion
│   └── ingest_countries.py # Country-by-country ranking ingestion
├── sql/
│   ├── 01_schema.sql       # Tables, indexes, constraints, tier function
│   ├── 02_queries.sql      # 6 complex analytical queries
│   ├── 03_views.sql        # Views: player_performance_summary, improvement_coach
│   └── 04_procedures.sql   # Stored procedures: upsert_player, refresh_rank_tier_averages
└── .env                    # Credentials (not committed — see below)
```

---

## Features

- **Player Search** : search any osu! username to view their full profile, top scores, rank tier, and performance metrics
- **Improvement Coach** : personalised tips based on PP, accuracy, play count, and star rating compared to the player's tier average. Includes PP Farm map recommendations and accuracy improvement suggestions
- **Rank Analysis** : bar charts showing average PP and accuracy per rank tier, plus mod usage statistics (powered by Matplotlib)
- **Beatmap Explorer** : scatter plot of star rating vs average PP across all beatmaps in the database (powered by Matplotlib)
- **Admin Panel** : ingest new players from the osu! API, refresh tier averages, and remove players. Password protected

---

## Environment Variables

The `.env` file is not included in the repository as it contains credentials. Create your own using the template in the Setup section above.

---

## Admin Access

Navigate to `/admin`, password is `admin`.
