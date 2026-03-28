# ✈️ Perak Flight Analytics Dashboard

A real-time IoT data acquisition and analytics system that continuously monitors aircraft flying over **Perak, Malaysia**. Built with Flask, the dashboard visualizes historical flight telemetry collected from a Raspberry Pi over multiple days.

---

## 📌 Project Overview

This project implements a full IoT data pipeline:

1. A **Raspberry Pi** polls the OpenSky Network API every few minutes, capturing live aircraft state vectors over Perak airspace.
2. Flight telemetry is stored persistently in a **SQLite database**.
3. A **Flask backend** performs analytics using Pandas and exposes REST API endpoints.
4. An **interactive dashboard** visualizes all analytics through charts, maps, and tables.
5. A **bonus feature** mathematically infers departure/arrival airport GPS coordinates directly from collected flight trajectory data.

---

## 📊 Dashboard Features

| Feature | Description |
|---|---|
| **Flights / Hour** | Hourly air traffic patterns to identify peak flight periods |
| **Flights / Day** | Daily flight activity trend over the collection period |
| **KPI Summary** | Total recorded flights, average altitude (m), average velocity (m/s) |
| **Flight Path Map** | Geographic visualization of all recorded aircraft positions over Perak |
| **Country Distribution** | Donut chart of aircraft registration countries |
| **Altitude Distribution** | Histogram of aircraft altitude ranges |
| **Velocity Distribution** | Histogram of aircraft speed distribution |
| **Inferred Airport Locations** |  GPS coordinates of airports inferred from flight trajectory data |

---

## 🧰 Technology Stack

- **Python** — Core language
- **Flask** — Web framework and REST API
- **Pandas** — Data processing and analytics
- **SQLite** — Local database (built into Python)
- **OpenSky Network API** — Live aircraft telemetry source
- **Leaflet.js** — Interactive map visualization
- **Chart.js** — Charts and graphs
- **Render** — Cloud deployment

---

## 🌐 Live Demo

Deployed on **Render** — accessible online without any installation.

🔗 **Live Dashboard:** [https://iot-jan-26.onrender.com](https://iot-jan-26.onrender.com)

---

## 🚀 Local Setup

### 1. Install Python
Download from [python.org](https://www.python.org/downloads/) — ensure **"Add Python to PATH"** is checked.

```bash
python --version
```

### 2. Install Git
Download from [git-scm.com](https://git-scm.com/downloads)

### 3. Clone Repository
```bash
git clone https://github.com/Tanycy/IoT_Jan_26.git
cd IoT_Jan_26
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run Inference (first time only)
```bash
python infer_airports.py
```

### 6. Start the Server
```bash
python app.py
```

Open: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 📂 Project Structure

```
IoT_Jan_26/
│
├── app.py                 ← Flask server + REST API endpoints
├── collect_data.py        ← RPi data collector (OpenSky API polling)
├── infer_airports.py      ← Airport GPS inference from trajectory data
├── airports.csv           ← Airport reference data (OurAirports)
├── perak_flights.db       ← SQLite database with all collected data
├── requirements.txt       ← Python dependencies
│
├── templates/
│   └── dashboard.html     ← Interactive dashboard UI
│
└── README.md
```

---

## 🗄️ Database Schema

```
flights              ← raw telemetry from OpenSky (icao24, callsign, lat, lon, alt, vel)
inferred_airports    ← GPS coordinates inferred from flight trajectory data
```

---

## ⚠️ Important Notes

- Do **NOT** modify `perak_flights.db` — it contains all collected historical data
- `airports.csv` is auto-downloaded on first run if missing
- Only **Python** and **Git** are required to run locally — SQLite is built into Python
