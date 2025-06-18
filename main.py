# ──────────────────────────────────────────────────────────────────────────────
#  Multi-Sensor-Gateway for ESP32 Payload (FastAPI Implementation)
#  Receives, logs, and periodically uploads the most recent sensor data to Supabase.
# ──────────────────────────────────────────────────────────────────────────────

import os
import json
import asyncio
from fastapi import FastAPI, Request
from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# ──────────────────────────────────────────────────────────────────────────────
#  Environment and Logging Setup
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = "sensor_data"
SUPABASE_ENABLED = SUPABASE_URL and SUPABASE_KEY

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sensor_payloads.log"),
        logging.StreamHandler()
    ]
)

# ──────────────────────────────────────────────────────────────────────────────
#  INIR2 Methane Sensor Constants and Decoding Tables
# ──────────────────────────────────────────────────────────────────────────────
START_WORD = 0x0000005B
END_WORD   = 0x0000005D
MASK32     = 0xFFFFFFFF

SUBSYS = [
    "Gas Sensor", "Power / Reset", "ADC", "DAC", "UART",
    "Timer / Counter", "General", "Memory"
]

FAULT_TABLE = {
    0: {1: "Sensor not present",
        2: "Temperature sensor defective or out of spec",
        3: "Active/reference signal too weak",
        4: "Initial configuration – no settings saved"},
    1: {1: "Power-On Reset",
        2: "Watchdog Reset",
        3: "Software Reset",
        4: "External Reset (Pin)"},
    2: {1: "Gas concentration not stable"},
    3: {1: "DAC turned off",
        2: "DAC disabled in config mode"},
    4: {1: "UART break longer than word length",
        2: "Framing error",
        3: "Parity error",
        4: "Overrun error"},
    5: {1: "Timer1 error",
        2: "Timer2 or Watchdog error"},
    6: {1: "Overrange",
        2: "Underrange",
        3: "Warm-Up (invalid measurement)"},
    7: {1: "Flash write failed",
        2: "Flash read failed"}
}

def calc_crc(words: List[int]) -> int:
    """
    Computes the 32-bit CRC as an unweighted byte sum of all 32-bit words
    in the frame (little-endian interpretation).
    """
    s = 0
    for w in words:
        for i in range(4):
            s += (w >> (8 * i)) & 0xFF
    return s & MASK32

def validate_crc(payload: List[int], crc: int, inv_crc: int) -> bool:
    """
    Validates CRC and its one's complement as per the protocol specification.
    """
    val = calc_crc(payload)
    return val == crc and (val ^ MASK32) == inv_crc

def decode_faults(fault_word: int) -> List[str]:
    """
    Decodes the 32-bit fault word using 4-bit nibbles.
    Nibble value 0xA means 'no error' for the subsystem.
    """
    messages = []
    for idx in range(8):  # 0 = least significant nibble
        nibble = (fault_word >> (idx * 4)) & 0xF
        if nibble == 0xA:
            continue  # No error for this subsystem
        text = FAULT_TABLE.get(idx, {}).get(
            nibble,
            f"Unknown code 0x{nibble:X} in subsystem {SUBSYS[idx]}"
        )
        messages.append(f"{SUBSYS[idx]}: {text}")
    return messages or ["No errors detected"]

@dataclass
class MethaneSensorPacket:
    concentration_ppm: int
    fault_word: int
    temperature_kx10: int
    crc: int
    inv_crc: int

    @property
    def temperature_C(self) -> float:
        """Returns temperature in degrees Celsius."""
        return self.temperature_kx10 / 10.0 - 273.15

    @property
    def concentration_percent(self) -> float:
        """Returns methane concentration as percent by volume."""
        return self.concentration_ppm / 10000.0

    def fault_messages(self) -> List[str]:
        """Returns decoded fault messages for all subsystems."""
        return decode_faults(self.fault_word)

def parse_inir_payload(hex_words: List[str]) -> MethaneSensorPacket:
    """
    Parses a list of seven hex-strings into a MethaneSensorPacket and
    performs all necessary plausibility and CRC checks.
    Raises ValueError on malformed payloads.
    """
    if len(hex_words) != 7:
        raise ValueError("Exactly seven 32-bit words are expected for the methane sensor frame.")
    words = [int(w, 16) for w in hex_words]
    if words[0] != START_WORD or words[-1] != END_WORD:
        raise ValueError("Start or end marker is invalid in the methane sensor frame.")
    if not validate_crc(words[:4], words[4], words[5]):
        raise ValueError("CRC validation failed for the methane sensor frame.")
    return MethaneSensorPacket(
        concentration_ppm=words[1],
        fault_word=words[2],
        temperature_kx10=words[3],
        crc=words[4],
        inv_crc=words[5]
    )

# ──────────────────────────────────────────────────────────────────────────────
#  FastAPI App, Data Buffer, and Upload Task
# ──────────────────────────────────────────────────────────────────────────────

# Buffer for the latest received entry and last upload timestamp
LAST_RECEIVED_ENTRY: Dict[str, Any] = {}
LAST_UPLOAD_TIMESTAMP: str = ""

app = FastAPI(
    title="ESP32 Multi-Sensor Gateway",
    description=(
        "Receives and processes payloads from an ESP32-based sensor system, "
        "including environmental sensors (pH, BME680, temperature) and INIR2 methane sensor."
    )
)

@app.on_event("startup")
async def startup_event():
    # Start background upload task
    if SUPABASE_ENABLED:
        asyncio.create_task(periodic_supabase_upload())

@app.post("/data")
async def receive_data(request: Request) -> Dict[str, Any]:
    """
    Receives sensor data as JSON payload, applies data filtering and decoding, and returns results.
    The expected payload is:
    {
        "ph": <float>,
        "ph_voltage": <float>,
        "temp1": <float>,
        "temp2": <float>,
        "bme_temperature": <float>,
        "bme_humidity": <float>,
        "bme_pressure": <float>,
        "bme_gas_resistance": <float>,
        "methan_raw": ["0000005b", ... , "0000005d"]
    }
    """
    body = await request.json()

    def filter_temperature(val):
        return val if isinstance(val, (int, float)) and 15.0 <= val <= 50.0 else float("nan")

    temp1_raw = body.get("temp1")
    temp2_raw = body.get("temp2")
    temp1 = filter_temperature(temp1_raw)
    temp2 = filter_temperature(temp2_raw)

    methan_raw = body.get("methan_raw", [])
    methane_result = None
    methane_error = None
    if isinstance(methan_raw, list) and len(methan_raw) == 7:
        try:
            packet = parse_inir_payload(methan_raw)
            methane_result = {
                "concentration_ppm": packet.concentration_ppm,
                "concentration_percent": round(packet.concentration_percent, 5),
                "temperature_C": round(packet.temperature_C, 2),
                "faults": packet.fault_messages()
            }
        except Exception as err:
            methane_error = str(err)
    else:
        methane_error = "Methane raw payload missing or invalid format"

    # Log entry (as JSON with UTC timestamp)
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "ph": body.get("ph"),
        "ph_voltage": body.get("ph_voltage"),
        "temp1": temp1,
        "temp2": temp2,
        "bme_temperature": body.get("bme_temperature"),
        "bme_humidity": body.get("bme_humidity"),
        "bme_pressure": body.get("bme_pressure"),
        "bme_gas_resistance": body.get("bme_gas_resistance"),
        "methan_raw": methan_raw,
        "methane_ppm": methane_result["concentration_ppm"] if methane_result else None,
        "methane_percent": methane_result["concentration_percent"] if methane_result else None,
        "methane_temperature": methane_result["temperature_C"] if methane_result else None,
        "methane_faults": methane_result["faults"] if methane_result else methane_error,
    }
    # Write to log file
    logging.info(json.dumps(log_entry, ensure_ascii=False))

    # Print result in console
    print("\n📥  New Sensor Data Received")
    for key, val in log_entry.items():
        print(f"   {key}: {val}")

    # Save as the latest entry (for periodic upload)
    global LAST_RECEIVED_ENTRY
    LAST_RECEIVED_ENTRY = log_entry.copy()

    return {
        "status": "ok" if methane_result else "warning",
        "message": methane_error if methane_error else "Valid data.",
        **log_entry
    }

async def periodic_supabase_upload():
    """
    Periodically uploads the latest received sensor data to Supabase every 10 seconds,
    only if the data is new (timestamp differs from last upload).
    """
    if not SUPABASE_ENABLED:
        logging.warning("Supabase not configured. Data will not be uploaded.")
        return
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    global LAST_RECEIVED_ENTRY, LAST_UPLOAD_TIMESTAMP
    while True:
        await asyncio.sleep(10)
        if LAST_RECEIVED_ENTRY:
            current_ts = LAST_RECEIVED_ENTRY.get("timestamp")
            if current_ts and current_ts != LAST_UPLOAD_TIMESTAMP:
                try:
                    response = supabase.table(SUPABASE_TABLE).insert([LAST_RECEIVED_ENTRY]).execute()
                    logging.info("Uploaded latest record to Supabase.")
                    print("✅ Supabase upload successful: latest record.")
                    LAST_UPLOAD_TIMESTAMP = current_ts
                except Exception as e:
                    logging.error(f"Supabase upload failed: {e}")
                    print(f"❌ Supabase upload failed: {e}")
            else:
                logging.info("No new data to upload.")
        else:
            logging.info("No data received yet.")

# ──────────────────────────────────────────────────────────────────────────────
#  Stand-Alone Run / Development Entry Point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
