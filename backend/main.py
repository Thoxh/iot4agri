# ──────────────────────────────────────────────────────────────────────────────
#  Smart Biodigester Sensor Backend - Multi-Sensor Gateway
# ──────────────────────────────────────────────────────────────────────────────
"""
Smart Biodigester Monitoring System - Backend API Server

This FastAPI-based backend server receives, processes, and stores sensor data from
an ESP32-based multi-sensor system monitoring a smart biodigester. The system handles
various sensor types including environmental sensors, pH measurement, temperature
monitoring, and specialized methane gas detection.

Key Features:
- Real-time sensor data reception via HTTP POST endpoints
- INIR2 methane sensor protocol decoding with CRC validation
- Temperature value persistence for sensor reliability
- Automatic data logging to files and console
- Periodic Supabase database uploads
- Comprehensive error handling and fault detection
- German timezone support for accurate timestamps

Supported Sensors:
- pH sensor with voltage monitoring
- Dual temperature sensors (temp1, temp2) with validation
- BME680 environmental sensor (temperature, humidity, pressure, gas resistance)
- INIR2 methane sensor with fault detection and CRC validation

Data Flow:
1. ESP32 sends JSON payload via HTTP POST to /data endpoint
2. Backend validates and processes sensor data
3. Temperature values are filtered and persisted
4. Methane sensor data is decoded using INIR2 protocol
5. Processed data is logged and stored in memory
6. Periodic background task uploads data to Supabase every 10 seconds

Author: Tim Siebert & Max Zboralski
Version: 1.0.0
Date: 2025-08-31
Python: 3.8+
Framework: FastAPI
"""

# Standard library imports
import json
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# Third-party imports
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from supabase import create_client, Client
import pytz

# ──────────────────────────────────────────────────────────────────────────────
#  Environment Configuration and Database Setup
# ──────────────────────────────────────────────────────────────────────────────

# Load environment variables from .env file
load_dotenv()

# Supabase database configuration
SUPABASE_TABLE = "sensor_data"  # Database table name for sensor data storage
SUPABASE_ENABLED = SUPABASE_URL and SUPABASE_KEY  # Enable Supabase uploads if configured

# Timezone configuration for German timestamps (Europe/Berlin)
# All timestamps are converted to German timezone for consistency
GERMAN_TZ = pytz.timezone('Europe/Berlin')

# ──────────────────────────────────────────────────────────────────────────────
#  Logging Configuration
# ──────────────────────────────────────────────────────────────────────────────

# Configure comprehensive logging to both file and console
# Log file: sensor_payloads.log contains all sensor data and system events
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sensor_payloads.log"),  # File logging for persistence
        logging.StreamHandler()  # Console logging for development
    ]
)

# ──────────────────────────────────────────────────────────────────────────────
#  Temperature Value Persistence and Sensor Reliability
# ──────────────────────────────────────────────────────────────────────────────

# Global variables to store last valid temperature readings for sensor reliability
# These values are used when current sensor readings are outside the valid range (15-50°C)
# This approach ensures continuous temperature monitoring even with temporary sensor failures
LAST_VALID_TEMP1: Optional[float] = None  # Last valid reading from temperature sensor 1
LAST_VALID_TEMP2: Optional[float] = None  # Last valid reading from temperature sensor 2

# ──────────────────────────────────────────────────────────────────────────────
#  INIR2 Methane Sensor Protocol Constants and Decoding Tables
# ──────────────────────────────────────────────────────────────────────────────

# INIR2 protocol frame markers and constants
# The INIR2 methane sensor uses a specific protocol with start/end markers and CRC validation
START_WORD = 0x0000005B  # Protocol frame start marker
END_WORD   = 0x0000005D  # Protocol frame end marker
MASK32     = 0xFFFFFFFF  # 32-bit mask for data processing

# Subsystem identifiers for fault decoding
# Each subsystem can report specific fault conditions via 4-bit nibbles
SUBSYS = [
    "Gas Sensor",      # Index 0: Main gas detection subsystem
    "Power / Reset",   # Index 1: Power management and reset conditions
    "ADC",             # Index 2: Analog-to-digital converter
    "DAC",             # Index 3: Digital-to-analog converter
    "UART",            # Index 4: Serial communication interface
    "Timer / Counter", # Index 5: Timing and counting subsystem
    "General",         # Index 6: General system faults
    "Memory"           # Index 7: Memory-related errors
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
    Computes the 32-bit CRC checksum for INIR2 protocol validation.
    
    The CRC is calculated as an unweighted byte sum of all 32-bit words
    in the frame using little-endian interpretation. This provides basic
    data integrity checking for the methane sensor communication protocol.
    
    Args:
        words (List[int]): List of 32-bit integers representing the data frame
        
    Returns:
        int: 32-bit CRC checksum value
        
    Example:
        >>> calc_crc([0x12345678, 0x9ABCDEF0])
        3735928559
    """
    s = 0
    for w in words:
        for i in range(4):
            s += (w >> (8 * i)) & 0xFF
    return s & MASK32

def validate_crc(payload: List[int], crc: int, inv_crc: int) -> bool:
    """
    Validates CRC and its one's complement according to INIR2 protocol specification.
    
    The INIR2 protocol requires both the CRC and its bitwise complement for
    enhanced error detection. This function verifies both values match the
    calculated checksum from the payload data.
    
    Args:
        payload (List[int]): Data payload to validate
        crc (int): Received CRC value from the sensor
        inv_crc (int): Received inverted CRC value from the sensor
        
    Returns:
        bool: True if both CRC and inverted CRC are valid, False otherwise
        
    Example:
        >>> validate_crc([0x1234, 0x5678], 0x68AC, 0x9753)
        True
    """
    expected_crc = calc_crc(payload)
    return crc == expected_crc and inv_crc == (~expected_crc & MASK32)

def decode_faults(fault_word: int) -> List[str]:
    """
    Decodes the 32-bit fault word from INIR2 methane sensor into human-readable messages.
    
    The fault word contains 8 subsystems, each represented by a 4-bit nibble.
    A nibble value of 0xA indicates 'no error' for that subsystem. Other values
    correspond to specific fault conditions defined in the FAULT_TABLE.
    
    Args:
        fault_word (int): 32-bit fault word from the sensor
        
    Returns:
        List[str]: List of human-readable fault messages
        
    Example:
        >>> decode_faults(0x12345678)
        ['Gas Sensor: Sensor not present', 'Power / Reset: Watchdog Reset']
    """
    faults = []
    for i in range(8):  # Process all 8 subsystems
        nibble = (fault_word >> (i * 4)) & 0xF  # Extract 4-bit nibble
        if nibble != 0xA:  # 0xA means "no error"
            subsystem = SUBSYS[i]
            if i in FAULT_TABLE and nibble in FAULT_TABLE[i]:
                fault_desc = FAULT_TABLE[i][nibble]
                faults.append(f"{subsystem}: {fault_desc}")
            else:
                faults.append(f"{subsystem}: Unknown fault code {nibble}")
    return faults or ["No errors detected"]


@dataclass
class MethaneSensorPacket:
    """
    Data structure representing a decoded INIR2 methane sensor packet.
    
    This class encapsulates all data fields from a complete INIR2 protocol frame,
    including methane concentration, temperature, fault information, and CRC values.
    It provides convenient methods for unit conversion and fault interpretation.
    
    Attributes:
        concentration_ppm (int): Methane concentration in parts per million
        fault_word (int): 32-bit fault word containing subsystem status information
        temperature_kx10 (int): Temperature in Kelvin * 10 (raw sensor value)
        crc (int): CRC checksum value from the sensor
        inv_crc (int): Inverted CRC checksum for enhanced error detection
    """
    concentration_ppm: int
    fault_word: int
    temperature_kx10: int
    crc: int
    inv_crc: int

    @property
    def temperature_C(self) -> float:
        """
        Returns temperature in degrees Celsius.
        
        Converts the raw temperature value from Kelvin*10 to Celsius.
        
        Returns:
            float: Temperature in degrees Celsius
            
        Example:
            >>> packet.temperature_kx10 = 2980  # 298.0 K
            >>> packet.temperature_C
            24.85
        """
        return self.temperature_kx10 / 10.0 - 273.15

    @property
    def concentration_percent(self) -> float:
        """
        Returns methane concentration as percent by volume.
        
        Converts concentration from ppm to percentage (0-100%).
        
        Returns:
            float: Methane concentration as percentage
            
        Example:
            >>> packet.concentration_ppm = 50000  # 5% methane
            >>> packet.concentration_percent
            5.0
        """
        return self.concentration_ppm / 10000.0

    def fault_messages(self) -> List[str]:
        """
        Returns decoded fault messages for all subsystems.
        
        Decodes the fault_word into human-readable error messages
        for each subsystem in the INIR2 sensor.
        
        Returns:
            List[str]: List of fault messages or ["No errors detected"]
            
        Example:
            >>> packet.fault_messages()
            ['Gas Sensor: Sensor not present', 'UART: Framing error']
        """
        return decode_faults(self.fault_word)

def parse_inir_payload(hex_words: List[str]) -> MethaneSensorPacket:
    """
    Parses INIR2 methane sensor payload and performs comprehensive validation.
    
    This function processes a complete INIR2 protocol frame consisting of 7 hex words:
    - Word 0: Start marker (0x0000005B)
    - Word 1: Methane concentration in ppm
    - Word 2: Fault word (32-bit subsystem status)
    - Word 3: Temperature in Kelvin * 10
    - Word 4: CRC checksum
    - Word 5: Inverted CRC checksum
    - Word 6: End marker (0x0000005D)
    
    The function validates frame markers, performs CRC verification, and creates
    a MethaneSensorPacket with all decoded values.
    
    Args:
        hex_words (List[str]): List of 7 hex strings representing the INIR2 frame
        
    Returns:
        MethaneSensorPacket: Validated and decoded sensor data packet
        
    Raises:
        ValueError: If payload format is invalid, CRC check fails, or frame markers are wrong
        
    Example:
        >>> hex_data = ['0000005b', '00001234', '0000aaaa', '00000bb8', '12345678', '87654321', '0000005d']
        >>> packet = parse_inir_payload(hex_data)
        >>> packet.concentration_ppm
        4660
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

def get_german_timestamp() -> str:
    """
    Returns current timestamp in German timezone (Europe/Berlin) as ISO format string.
    
    All timestamps in the system are standardized to German timezone for consistency
    across the biodigester monitoring system. This ensures proper correlation with
    local operational schedules and maintenance windows.
    
    Returns:
        str: ISO format timestamp string in German timezone
        
    Example:
        >>> get_german_timestamp()
        '2025-08-31T14:30:45.123456+02:00'
    """
    return datetime.now(GERMAN_TZ).isoformat()

def get_persistent_temperature(val: Any, last_valid: Optional[float]) -> Optional[float]:
    """
    Returns temperature value with persistence logic for sensor reliability.
    
    This function implements a persistence mechanism for temperature sensors to handle
    temporary sensor failures or out-of-range readings. Valid temperature range is
    defined as 15-50°C based on expected biodigester operating conditions.
    
    Logic:
    1. If current value is valid (15-50°C), return it
    2. If current value is invalid, return the last valid reading
    3. If no valid reading exists, return None
    
    Args:
        val (Any): Current temperature reading from sensor
        last_valid (Optional[float]): Last known valid temperature reading
        
    Returns:
        Optional[float]: Valid temperature value or None if no valid data available
        
    Example:
        >>> get_persistent_temperature(25.5, None)
        25.5
        >>> get_persistent_temperature(-10.0, 23.4)
        23.4
    """
    global LAST_VALID_TEMP1, LAST_VALID_TEMP2
    
    # Check if current value is within valid range (15-50°C)
    if isinstance(val, (int, float)) and 15.0 <= val <= 50.0:
        return val  # Return current valid value
    
    # Current value is invalid, return last valid value for continuity
    return last_valid

# ──────────────────────────────────────────────────────────────────────────────
#  FastAPI Application Configuration and Global State Management
# ──────────────────────────────────────────────────────────────────────────────

# Global state variables for data buffering and upload tracking
# These variables maintain the latest sensor data and upload status across requests
LAST_RECEIVED_ENTRY: Dict[str, Any] = {}  # Buffer for the most recent sensor data entry
LAST_UPLOAD_TIMESTAMP: str = ""  # Timestamp of the last successful Supabase upload

# FastAPI application instance with comprehensive API documentation
app = FastAPI(
    title="Smart Biodigester Sensor Backend",
    description=(
        "Production-ready FastAPI server for the Smart Biodigester monitoring system. "
        "Receives and processes multi-sensor payloads from ESP32-based hardware, "
        "including environmental sensors (pH, BME680, temperature) and specialized "
        "INIR2 methane sensor with protocol decoding and CRC validation."
    ),
    version="2.0.0",
    docs_url="/docs",  # Swagger UI documentation endpoint
    redoc_url="/redoc"  # ReDoc documentation endpoint
)

@app.on_event("startup")
async def startup_event():
    """
    FastAPI startup event handler for initializing background tasks.
    
    This function is called once when the FastAPI application starts up.
    It initializes the periodic Supabase upload task if database integration
    is enabled, ensuring continuous data synchronization.
    
    Background Tasks:
    - Periodic Supabase upload task (runs every 10 seconds)
    - Only started if SUPABASE_ENABLED is True
    """
    logging.info("🚀 Smart Biodigester Backend starting up...")
    
    # Start background upload task if Supabase is configured
    if SUPABASE_ENABLED:
        asyncio.create_task(periodic_supabase_upload())
        logging.info("✅ Periodic Supabase upload task started")
    else:
        logging.warning("⚠️ Supabase not configured - data will not be uploaded to database")

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
    # Access global temperature persistence variables
    global LAST_VALID_TEMP1, LAST_VALID_TEMP2
    
    # Parse incoming JSON payload from ESP32 sensor system
    body = await request.json()

    # Extract raw temperature values from payload
    temp1_raw = body.get("temp1")  # Tank temperature sensor 1
    temp2_raw = body.get("temp2")  # Tank temperature sensor 2
    
    # Apply temperature persistence logic to ensure data continuity
    # Uses last valid values when current readings are invalid or out of range
    temp1 = get_persistent_temperature(temp1_raw, LAST_VALID_TEMP1)
    temp2 = get_persistent_temperature(temp2_raw, LAST_VALID_TEMP2)
    
    # Update global temperature persistence state for temp1
    # Valid range: 15.0°C to 50.0°C (biodigester operational range)
    if isinstance(temp1_raw, (int, float)) and 15.0 <= temp1_raw <= 50.0:
        LAST_VALID_TEMP1 = temp1_raw
        logging.info(f"✅ Updated LAST_VALID_TEMP1 to: {LAST_VALID_TEMP1}°C")
    else:
        logging.info(f"⚠️ Temp1 invalid ({temp1_raw}), using last valid: {LAST_VALID_TEMP1}°C")
        
    # Update global temperature persistence state for temp2
    # Same validation range as temp1 for consistency
    if isinstance(temp2_raw, (int, float)) and 15.0 <= temp2_raw <= 50.0:
        LAST_VALID_TEMP2 = temp2_raw
        logging.info(f"✅ Updated LAST_VALID_TEMP2 to: {LAST_VALID_TEMP2}°C")
    else:
        logging.info(f"⚠️ Temp2 invalid ({temp2_raw}), using last valid: {LAST_VALID_TEMP2}°C")

    # Process INIR2 methane sensor data with protocol decoding
    methan_raw = body.get("methan_raw", [])  # Expected: 7-element hex string array
    methane_result = None  # Successful parsing result
    methane_error = None   # Error message if parsing fails
    
    # Validate INIR2 payload format (must be exactly 7 hex strings)
    if isinstance(methan_raw, list) and len(methan_raw) == 7:
        try:
            # Parse INIR2 protocol payload with CRC validation
            packet = parse_inir_payload(methan_raw)
            
            # Extract processed methane sensor data
            methane_result = {
                "concentration_ppm": packet.concentration_ppm,           # Parts per million
                "concentration_percent": round(packet.concentration_percent, 5),  # Percentage (0-100%)
                "temperature_C": round(packet.temperature_C, 2),         # Sensor internal temperature
                "faults": packet.fault_messages()                       # Human-readable fault messages
            }
        except Exception as err:
            methane_error = str(err)
    else:
        methane_error = "Methane raw payload missing or invalid format"

    # Log entry (as JSON with German timezone timestamp)
    log_entry = {
        "timestamp": get_german_timestamp(),
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
    print(f"   📌 Last valid temp1: {LAST_VALID_TEMP1}")
    print(f"   📌 Last valid temp2: {LAST_VALID_TEMP2}")

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
    uvicorn.run(app, host="0.0.0.0", port=5000)
