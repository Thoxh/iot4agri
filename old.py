import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

import logging
from logging.handlers import RotatingFileHandler

# Logger Setup
logger = logging.getLogger("biodigester")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

file_handler = RotatingFileHandler("app.log", maxBytes=1_000_000, backupCount=3)
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Mapping: Feldname -> sensor_id (aus Tabelle sensors)
SENSOR_FIELD_TO_ID = {
    "air_temperature": 1,
    "gas_pressure": 2,
    "pH": 3,
    "slurry_temperature": 4,
    "air_humidity": 5,
    "methane_concentration": 6,
}

class SensorPayload(BaseModel):
    air_temperature: float | None = None
    gas_pressure: float | None = None
    pH: float | None = None
    slurry_temperature: float | None = None
    air_humidity: float | None = None
    methane_concentration: float | None = None

from fastapi import Request

@app.post("/sensor-data")
async def receive_sensor_data(request: Request):
    raw_body = await request.body()
    logger.info(f"RAW sensor payload: {raw_body.decode('utf-8')}")
    try:
        data = await request.json()
        # Transformiere falls ESP-Format
        if "fields" in data:
            transformed = {}
            for key, val in data["fields"].items():
                # Extrahiere doubleValue, fallback auf None
                transformed[key] = val.get("doubleValue")
            payload = SensorPayload(**transformed)
        else:
            payload = SensorPayload(**data)
    except Exception as e:
        logger.error(f"Pydantic validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    logger.info(f"Parsed sensor payload: {payload.model_dump()}")
    # Supabase Insert: sensor_readings + sensor_values
    try:
        # 1. Insert sensor_readings (timestamp: jetzt)
        from datetime import datetime, timezone
        reading_result = supabase.table("sensor_readings").insert({
            "timestamp": datetime.now(timezone.utc).isoformat()
        }).execute()
        if not reading_result.data or not reading_result.data[0].get("id"):
            raise Exception("Failed to insert sensor_readings")
        reading_id = reading_result.data[0]["id"]
        logger.info(f"Inserted sensor_readings id={reading_id}")

        # 2. Insert sensor_values für jede gemessene Größe
        values_to_insert = []
        for field, value in payload.model_dump().items():
            if value is not None and field in SENSOR_FIELD_TO_ID:
                values_to_insert.append({
                    "reading_id": reading_id,
                    "sensor_id": SENSOR_FIELD_TO_ID[field],
                    "value": value
                })
        if values_to_insert:
            values_result = supabase.table("sensor_values").insert(values_to_insert).execute()
            logger.info(f"Inserted {len(values_to_insert)} sensor_values for reading_id={reading_id}")
        else:
            logger.warning("No sensor values to insert!")
        return {"status": "success", "message": "Data uploaded to Supabase", "reading_id": reading_id}
    except Exception as e:
        logger.error(f"Supabase insert error: {e}")
        raise HTTPException(status_code=500, detail="Supabase insert failed")
