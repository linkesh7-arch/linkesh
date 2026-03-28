import requests
import pandas as pd
import sqlite3
import time
from datetime import datetime

# =========================
# 1. PERAK AREA COORDINATES
# =========================
lat_min = 3.5
lat_max = 5.8
lon_min = 100.3
lon_max = 101.5


# =========================
# 2. OPENSKY API (ADD YOUR LOGIN IF YOU HAVE)
# =========================
user_name = ""      # optional
password = ""       # optional

url_data = (
    "https://opensky-network.org/api/states/all?"
    f"lamin={lat_min}&lomin={lon_min}&lamax={lat_max}&lomax={lon_max}"
)

# =========================
# 3. SQLITE DATABASE SETUP
# =========================
conn = sqlite3.connect("perak_flights.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    icao24 TEXT,
    flight_number TEXT,
    origin_country TEXT,
    latitude REAL,
    longitude REAL,
    baro_altitude REAL,
    velocity REAL
)
""")
conn.commit()

# =========================
# 4. DATA COLLECTION LOOP
# =========================
print("Flight data collection started...")

while True:
    try:
        r = requests.get(url_data, timeout=30)

        print("Status code:", r.status_code)


        response = r.json()

        if response["states"] is None:
            print("No data received")
            time.sleep(300)
            continue

        col_name = [
            'icao24','flight_number','origin_country','time_position',
            'last_contact','longitude','latitude','baro_altitude',
            'on_ground','velocity','true_track','vertical_rate',
            'sensors','geo_altitude','squawk','spi','position_source'
        ]

        flight_df = pd.DataFrame(response["states"], columns=col_name)

        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 120)

        print("\n=== Sample Flight Data (Table View) ===")
        print(flight_df.head(10))

        # Keep only useful columns
        flight_df = flight_df[[
            'icao24','flight_number','origin_country',
            'latitude','longitude','baro_altitude','velocity'
        ]]

        flight_df["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        flight_df = flight_df.dropna(subset=["latitude", "longitude"])

        # Insert into SQLite
        flight_df.to_sql("flights", conn, if_exists="append", index=False)

        print(f"Saved {len(flight_df)} records at {datetime.now()}")

    except Exception as e:
        print("Error:", e)

    # Wait 5 minutes
    time.sleep(300)
