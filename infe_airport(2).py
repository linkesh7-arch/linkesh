import sqlite3
import pandas as pd
import numpy as np
import csv
import os

DB = "perak_flights.db"

# ── Load airports for nearest-name lookup ─────────────────────────────────
airports_df = None

def load_airports_df():
    global airports_df
    if not os.path.exists("airports.csv"):
        print("airports.csv not found!")
        return
    rows = []
    with open("airports.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            icao = row.get("icao_code", "").strip()
            lat  = row.get("latitude_deg", "")
            lon  = row.get("longitude_deg", "")
            name = row.get("name", "")
            city = row.get("municipality", "")
            if icao and lat and lon:
                try:
                    rows.append({
                        "icao": icao,
                        "name": name,
                        "city": city,
                        "lat":  float(lat),
                        "lon":  float(lon)
                    })
                except:
                    pass
    airports_df = pd.DataFrame(rows)
    print(f"Loaded {len(airports_df)} airports for name lookup.")

def nearest_airport(est_lat, est_lon):
    """Find the nearest airport to inferred GPS coordinates."""
    if airports_df is None or len(airports_df) == 0:
        return "Unknown", ""
    # Simple Euclidean distance (good enough for nearby airports)
    airports_df["dist"] = np.sqrt(
        (airports_df["lat"] - est_lat) ** 2 +
        (airports_df["lon"] - est_lon) ** 2
    )
    nearest = airports_df.loc[airports_df["dist"].idxmin()]
    dist_deg = nearest["dist"]

    # Only accept if within ~2 degrees (~220km) — otherwise too far
    if dist_deg > 2.0:
        return "Remote location", ""

    name = nearest["name"]
    city = nearest["city"]
    icao = nearest["icao"]
    label = f"{city} - {name} ({icao})" if city else f"{name} ({icao})"
    return label, icao

# ── Main inference ────────────────────────────────────────────────────────
def infer_airport_locations():
    load_airports_df()

    conn = sqlite3.connect(DB)

    df = pd.read_sql_query("""
        SELECT flight_number, icao24, timestamp,
               latitude, longitude, baro_altitude, velocity
        FROM flights
        WHERE flight_number IS NOT NULL
          AND TRIM(flight_number) != ''
          AND baro_altitude IS NOT NULL
          AND velocity IS NOT NULL
        ORDER BY flight_number, timestamp
    """, conn)

    print(f"Total records: {len(df)}")
    print(f"Unique flights: {df['flight_number'].nunique()}")

    results = []

    for flight_number, group in df.groupby("flight_number"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        if len(group) < 2:
            continue

        alt_diff = group["baro_altitude"].diff()

        # ── Descending = approaching destination ──
        descending = alt_diff < -50
        if descending.sum() >= 2:
            desc_points = group[descending]
            if len(desc_points) >= 2:
                p1 = desc_points.iloc[-2]
                p2 = desc_points.iloc[-1]
                dlat = p2["latitude"]  - p1["latitude"]
                dlon = p2["longitude"] - p1["longitude"]
                dalt = p2["baro_altitude"] - p1["baro_altitude"]
                if dalt < 0:
                    steps = min(-p2["baro_altitude"] / dalt, 20)
                    est_lat = round(p2["latitude"]  + dlat * steps, 4)
                    est_lon = round(p2["longitude"] + dlon * steps, 4)
                    airport_name, airport_icao = nearest_airport(est_lat, est_lon)
                    results.append({
                        "flight_number": flight_number,
                        "type":          "destination",
                        "est_lat":       est_lat,
                        "est_lon":       est_lon,
                        "airport_name":  airport_name,
                        "airport_icao":  airport_icao,
                        "last_alt":      p2["baro_altitude"],
                        "last_vel":      p2["velocity"],
                        "confidence":    "high" if descending.sum() >= 3 else "medium"
                    })

        # ── Ascending = just departed origin ──
        ascending = alt_diff > 50
        if ascending.sum() >= 2:
            asc_points = group[ascending]
            if len(asc_points) >= 2:
                p1 = asc_points.iloc[0]
                p2 = asc_points.iloc[1]
                dlat = p2["latitude"]  - p1["latitude"]
                dlon = p2["longitude"] - p1["longitude"]
                dalt = p2["baro_altitude"] - p1["baro_altitude"]
                if dalt > 0:
                    steps = min(p1["baro_altitude"] / dalt, 20)
                    est_lat = round(p1["latitude"]  - dlat * steps, 4)
                    est_lon = round(p1["longitude"] - dlon * steps, 4)
                    airport_name, airport_icao = nearest_airport(est_lat, est_lon)
                    results.append({
                        "flight_number": flight_number,
                        "type":          "origin",
                        "est_lat":       est_lat,
                        "est_lon":       est_lon,
                        "airport_name":  airport_name,
                        "airport_icao":  airport_icao,
                        "last_alt":      p1["baro_altitude"],
                        "last_vel":      p1["velocity"],
                        "confidence":    "high" if ascending.sum() >= 3 else "medium"
                    })

    results_df = pd.DataFrame(results)
    if len(results_df) == 0:
        print("No inferences found.")
        conn.close()
        return

    print(f"\nInferred {len(results_df)} airport locations")

    # Save to DB
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS inferred_airports (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_number TEXT,
            type          TEXT,
            est_lat       REAL,
            est_lon       REAL,
            airport_name  TEXT,
            airport_icao  TEXT,
            last_alt      REAL,
            last_vel      REAL,
            confidence    TEXT,
            timestamp     TEXT DEFAULT (datetime('now'))
        )
    """)

    # Add columns if upgrading from old schema
    for col in ["airport_name TEXT", "airport_icao TEXT"]:
        try:
            c.execute(f"ALTER TABLE inferred_airports ADD COLUMN {col}")
        except:
            pass

    c.execute("DELETE FROM inferred_airports")

    for _, row in results_df.iterrows():
        c.execute("""
            INSERT INTO inferred_airports
            (flight_number, type, est_lat, est_lon, airport_name, airport_icao,
             last_alt, last_vel, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["flight_number"], row["type"],
            row["est_lat"], row["est_lon"],
            row["airport_name"], row["airport_icao"],
            row["last_alt"], row["last_vel"],
            row["confidence"]
        ))

    conn.commit()

    print(f"\n=== Summary ===")
    print(f"Origin inferences      : {len(results_df[results_df['type']=='origin'])}")
    print(f"Destination inferences : {len(results_df[results_df['type']=='destination'])}")
    print(f"High confidence        : {len(results_df[results_df['confidence']=='high'])}")
    print(f"\nSample inferred origins with airport names:")
    for _, r in results_df[results_df['type']=='origin'].head(8).iterrows():
        print(f"  {r['flight_number']:10} → ({r['est_lat']}, {r['est_lon']}) → {r['airport_name']} [{r['confidence']}]")

    conn.close()
    print("\nSaved to inferred_airports table!")

if __name__ == "__main__":
    infer_airport_locations()
