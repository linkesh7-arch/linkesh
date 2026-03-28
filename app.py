from flask import Flask, jsonify, render_template
import sqlite3
import pandas as pd
import requests
import time
import os
import csv
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
DB = "perak_flights.db"

# ─────────────────────────────────────────────
# 1.  AIRPORT LOOKUP  (OurAirports CSV)
#     Download once:
#     curl -o airports.csv https://ourairports.com/data/airports.csv
# ─────────────────────────────────────────────
AIRPORT_LOOKUP = {}   # icao_code -> airport name
CITY_LOOKUP    = {}   # icao_code -> municipality / city

def load_airports():
    csv_path = "airports.csv"
    if not os.path.exists(csv_path):
        print("airports.csv not found — downloading from OurAirports…")
        try:
            r = requests.get(
                "https://ourairports.com/data/airports.csv", timeout=30
            )
            with open(csv_path, "wb") as f:
                f.write(r.content)
            print("airports.csv downloaded.")
        except Exception as e:
            print("Could not download airports.csv:", e)
            return

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            icao = row.get("icao_code", "").strip()
            if icao:
                AIRPORT_LOOKUP[icao] = row.get("name", icao)
                CITY_LOOKUP[icao]    = row.get("municipality", "")

load_airports()   # runs once at startup

def icao_to_name(icao_code):
    """Return a human-readable airport name for an ICAO code."""
    if not icao_code:
        return "Unknown"
    name = AIRPORT_LOOKUP.get(icao_code)
    city = CITY_LOOKUP.get(icao_code, "")
    if name:
        return f"{name} ({icao_code})" if not city else f"{city} – {name} ({icao_code})"
    return icao_code   # fallback to raw ICAO


# ─────────────────────────────────────────────
# 2.  DATABASE HELPER
# ─────────────────────────────────────────────
def query_db(query, params=()):
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def ensure_routes_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flight_routes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            icao24           TEXT,
            flight_number    TEXT,
            departure_airport TEXT,
            arrival_airport  TEXT,
            departure_icao   TEXT,
            arrival_icao     TEXT,
            timestamp        TEXT
        )
    """)


# ─────────────────────────────────────────────
# 3.  OPENSKY ROUTE LOOKUP  (free, no API key)
# ─────────────────────────────────────────────
def lookup_route_opensky(callsign):
    """
    Returns (departure_icao, arrival_icao) or (None, None).
    OpenSky /routes endpoint: https://opensky-network.org/api/routes?callsign=MAS123
    Response: {"callsign": "MAS123", "route": ["WMKK", "WSSS"]}
    """
    try:
        url = "https://opensky-network.org/api/routes"
        r = requests.get(url, params={"callsign": callsign}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            route = data.get("route", [])
            if len(route) >= 2:
                return route[0], route[-1]
    except Exception as e:
        print(f"OpenSky route error for {callsign}: {e}")
    return None, None


# ─────────────────────────────────────────────
# 4.  SCHEDULED JOB  (every 5 min)
# ─────────────────────────────────────────────
def fetch_real_departures_job():
    print("⏱  Running scheduled departure fetch…")
    conn   = sqlite3.connect(DB)
    cursor = conn.cursor()
    ensure_routes_table(cursor)
    conn.commit()

    cursor.execute("""
        SELECT DISTINCT flight_number, icao24
        FROM flights
        WHERE flight_number IS NOT NULL
          AND TRIM(flight_number) != ''
        LIMIT 5
    """)
    flights = cursor.fetchall()

    for flight_number, icao24 in flights:
        flight_number = flight_number.strip()
        dep_icao, arr_icao = lookup_route_opensky(flight_number)

        if not dep_icao:
            continue

        cursor.execute("""
            INSERT INTO flight_routes
            (icao24, flight_number, departure_airport,
             arrival_airport, departure_icao, arrival_icao, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            icao24,
            flight_number,
            icao_to_name(dep_icao),
            icao_to_name(arr_icao),
            dep_icao,
            arr_icao,
            time.strftime("%Y-%m-%d %H:%M:%S")
        ))
        time.sleep(0.5)

    conn.commit()
    conn.close()
    print("✅ Scheduled fetch done.")


# ─────────────────────────────────────────────
# 5.  ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("dashboard.html")


# ── KPI summary ──────────────────────────────
@app.route("/api/summary")
def summary():
    df = query_db("SELECT * FROM flights")
    total    = len(df)
    avg_alt  = df["baro_altitude"].mean()
    avg_vel  = df["velocity"].mean()
    return jsonify({
        "total_flights":      int(total),
        "average_altitude":   round(float(avg_alt), 2) if avg_alt == avg_alt else 0,
        "average_velocity":   round(float(avg_vel), 2) if avg_vel == avg_vel else 0
    })


# ── Flights per hour ─────────────────────────
@app.route("/api/flights_per_hour")
def flights_per_hour():
    df = query_db("""
        SELECT strftime('%H:00', timestamp) AS hour_only,
               COUNT(*) AS count
        FROM flights
        GROUP BY hour_only
        ORDER BY hour_only
    """)
    return jsonify({"hours": df["hour_only"].tolist(), "counts": df["count"].tolist()})


# ── Flights per day ──────────────────────────
@app.route("/api/flights_per_day")
def flights_per_day():
    df = query_db("""
        SELECT date(timestamp) AS day, COUNT(*) AS count
        FROM flights
        GROUP BY day
        ORDER BY day
    """)
    return jsonify({"days": df["day"].tolist(), "counts": df["count"].tolist()})


# ── Top origin countries ─────────────────────
@app.route("/api/top_countries")
def top_countries():
    df = query_db("""
        SELECT origin_country, COUNT(*) AS count
        FROM flights
        GROUP BY origin_country
        ORDER BY count DESC
        LIMIT 10
    """)
    return jsonify({
        "countries": df["origin_country"].tolist(),
        "counts":    df["count"].tolist()
    })


# ── Altitude distribution ────────────────────
@app.route("/api/altitude_distribution")
def altitude_distribution():
    df   = query_db("SELECT baro_altitude FROM flights WHERE baro_altitude IS NOT NULL")
    bins = [0, 1000, 3000, 6000, 10000, 15000, 20000, 30000]
    hist = pd.cut(df["baro_altitude"], bins).value_counts().sort_index()
    return jsonify({"ranges": [str(x) for x in hist.index], "counts": hist.tolist()})


# ── Velocity distribution ────────────────────
@app.route("/api/velocity_distribution")
def velocity_distribution():
    df   = query_db("SELECT velocity FROM flights WHERE velocity IS NOT NULL")
    bins = [0, 100, 200, 300, 400, 500, 600]
    hist = pd.cut(df["velocity"], bins).value_counts().sort_index()
    return jsonify({"ranges": [str(x) for x in hist.index], "counts": hist.tolist()})


# ── Map data ─────────────────────────────────
@app.route("/api/map_data")
def map_data():
    df = query_db("""
        SELECT latitude, longitude
        FROM flights
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 500
    """)
    return jsonify(df.to_dict(orient="records"))


# ── Fetch routes on demand  (manual trigger) ─
@app.route("/api/fetch_real_departures")
def fetch_real_departures():
    conn   = sqlite3.connect(DB)
    cursor = conn.cursor()
    ensure_routes_table(cursor)
    conn.commit()

    cursor.execute("""
        SELECT DISTINCT flight_number, icao24
        FROM flights
        WHERE flight_number IS NOT NULL
          AND TRIM(flight_number) != ''
        LIMIT 10
    """)
    flights = cursor.fetchall()
    results = []

    for flight_number, icao24 in flights:
        flight_number = flight_number.strip()
        print(f"Looking up route for: {flight_number}")

        dep_icao, arr_icao = lookup_route_opensky(flight_number)

        if not dep_icao:
            print(f"  No route found for {flight_number}")
            continue

        dep_name = icao_to_name(dep_icao)
        arr_name = icao_to_name(arr_icao)

        cursor.execute("""
            INSERT INTO flight_routes
            (icao24, flight_number, departure_airport, arrival_airport,
             departure_icao, arrival_icao, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            icao24, flight_number,
            dep_name, arr_name,
            dep_icao, arr_icao,
            time.strftime("%Y-%m-%d %H:%M:%S")
        ))

        results.append({
            "flight_number":    flight_number,
            "departure_icao":   dep_icao,
            "departure_airport": dep_name,
            "arrival_icao":     arr_icao,
            "arrival_airport":  arr_name
        })
        time.sleep(0.5)

    conn.commit()
    conn.close()
    return jsonify(results)


# ── Departure airport summary for dashboard table ──
@app.route("/api/departure_airports")
def departure_airports():
    """
    Counts flight records per departure airport and includes
    inferred GPS coordinates from inferred_airports table.
    """
    try:
        df = query_db("""
            SELECT r.departure_airport,
                   r.departure_icao,
                   COUNT(f.id) AS count,
                   AVG(i.est_lat) AS inferred_lat,
                   AVG(i.est_lon) AS inferred_lon
            FROM flights f
            INNER JOIN flight_routes r
                ON f.flight_number = r.flight_number
            LEFT JOIN inferred_airports i
                ON f.flight_number = i.flight_number
                AND i.type = 'origin'
            WHERE r.departure_airport IS NOT NULL
              AND r.departure_airport != 'Unknown'
            GROUP BY r.departure_icao, r.departure_airport
            ORDER BY count DESC
            LIMIT 10
        """)
        if len(df) > 0:
            return jsonify([
                {
                    "airport":      row["departure_airport"],
                    "icao":         row["departure_icao"],
                    "count":        int(row["count"]),
                    "inferred_lat": round(float(row["inferred_lat"]), 4) if row["inferred_lat"] == row["inferred_lat"] else None,
                    "inferred_lon": round(float(row["inferred_lon"]), 4) if row["inferred_lon"] == row["inferred_lon"] else None
                }
                for _, row in df.iterrows()
            ])
    except Exception:
        pass

    # Fallback: use origin_country
    df = query_db("""
        SELECT origin_country AS airport, COUNT(*) AS count
        FROM flights
        GROUP BY origin_country
        ORDER BY count DESC
        LIMIT 10
    """)
    return jsonify([
        {"airport": row["airport"], "icao": "", "count": int(row["count"])}
        for _, row in df.iterrows()
    ])



# ── Inferred airport locations ────────────────
@app.route("/api/inferred_airports")
def inferred_airports():
    try:
        df = query_db("""
            SELECT flight_number, type, est_lat, est_lon,
                   airport_name, airport_icao,
                   last_alt, last_vel, confidence
            FROM inferred_airports
            WHERE confidence IN ('high', 'medium')
            ORDER BY confidence DESC, type
        """)
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify([])

# ─────────────────────────────────────────────
# 6.  SCHEDULER + STARTUP
# ─────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_real_departures_job, "interval", minutes=5)
scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
