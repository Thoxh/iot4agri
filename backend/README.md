# Smart Biodigester Monitor - Backend API

> FastAPI-based backend server for the Smart Biodigester Monitoring System

## 📋 Overview

The Smart Biodigester Backend is a high-performance FastAPI server that receives, processes, and stores sensor data from an ESP32-based multi-sensor system. The system supports various sensor types and implements specialized protocols for methane gas analysis.

### 🎯 Key Features

- **Real-time Data Reception**: HTTP POST endpoints for ESP32 sensor data
- **INIR2 Protocol Decoding**: Specialized methane sensor communication
- **Temperature Persistence**: Intelligent sensor failure handling
- **pH Calibration**: Automatic sensor adjustment (+9 offset)
- **Data Logging**: Comprehensive logging to files and console
- **Supabase Integration**: Periodic database uploads every 10 seconds
- **Error Handling**: Robust CRC validation and fault detection

### 🔬 Supported Sensors

- **pH Sensor**: With voltage monitoring and calibration
- **Dual Temperature Sensors**: temp1 & temp2 with validation (15-50°C)
- **BME680 Environmental Sensor**: Temperature, humidity, pressure, gas resistance
- **INIR2 Methane Sensor**: With fault detection and CRC validation

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip or poetry for package management
- Supabase project (optional for data storage)

### Installation

1. **Clone repository**
   ```bash
   git clone <repository-url>
   cd sensor-backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install fastapi uvicorn python-dotenv supabase pytz
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Configuration in `.env`:
   ```env
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   ```

5. **Start server**
   ```bash
   python main.py
   # or for development
   uvicorn main:app --host 0.0.0.0 --port 5000 --reload
   ```

6. **Test API**
   
   Server runs on: [http://localhost:5000](http://localhost:5000)
   
   API documentation: [http://localhost:5000/docs](http://localhost:5000/docs)

## 🏗️ Architecture

### Data Flow

```
ESP32 Sensors → HTTP POST /data → Backend Processing → Supabase Upload
     ↓                ↓                    ↓                    ↓
Sensor Data → JSON Payload → Validation/Calibration → Database
```

### Component Overview

```
sensor-backend/
├── main.py              # Main server application
├── .env                 # Environment variables (not in Git)
├── sensor_payloads.log  # Automatic data logging
└── README.md           # This documentation
```

## 📡 API Endpoints

### POST /data

Receives sensor data from ESP32 system.

**Request Body:**
```json
{
  "ph": 5.2,
  "ph_voltage": 2.1,
  "temp1": 35.5,
  "temp2": 34.8,
  "bme_temperature": 22.3,
  "bme_humidity": 65.2,
  "bme_pressure": 1013.25,
  "bme_gas_resistance": 50000,
  "methan_raw": ["0000005b", "00001234", "0000aaaa", "00000bb8", "12345678", "87654321", "0000005d"]
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Valid data.",
  "timestamp": "2025-08-31T14:30:45.123456+02:00",
  "ph": 14.2,
  "temp1": 35.5,
  "temp2": 34.8,
  "methane_ppm": 4660,
  "methane_percent": 0.466,
  "methane_temperature": 24.85,
  "methane_faults": ["No errors detected"]
}
```

## 🔧 Technical Details

### Temperature Persistence

The system implements intelligent temperature persistence:

- **Valid Range**: 15-50°C
- **Persistence Logic**: Invalid values use the last valid value
- **Logging**: All temperature validations are logged

```python
# Example of persistence logic
def get_persistent_temperature(val, last_valid):
    if isinstance(val, (int, float)) and 15.0 <= val <= 50.0:
        return val  # Current value is valid
    return last_valid  # Last valid value
```

### INIR2 Methane Sensor Protocol

The INIR2 protocol uses 7 32-bit words:

| Position | Description | Value |
|----------|-------------|-------|
| 0 | Start Marker | 0x0000005B |
| 1 | Methane Concentration (ppm) | Variable |
| 2 | Fault Word (32-bit) | Variable |
| 3 | Temperature (Kelvin × 10) | Variable |
| 4 | CRC Checksum | Variable |
| 5 | Inverted CRC | Variable |
| 6 | End Marker | 0x0000005D |

### pH Calibration

The pH sensor requires a calibration of +9:

```python
def adjust_ph_value(ph_raw):
    if isinstance(ph_raw, (int, float)):
        return ph_raw + 9  # Calibration offset
    return ph_raw
```

### Fault Detection

The system decodes 8 subsystems with 4-bit nibbles each:

- **0xA**: No error
- **Other Values**: Specific error codes (see FAULT_TABLE)

## 📊 Database Schema

### sensor_data Table

```sql
CREATE TABLE sensor_data (
  id SERIAL PRIMARY KEY,
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  ph DECIMAL,
  ph_voltage DECIMAL,
  temp1 DECIMAL,
  temp2 DECIMAL,
  bme_temperature DECIMAL,
  bme_humidity DECIMAL,
  bme_pressure DECIMAL,
  bme_gas_resistance DECIMAL,
  methan_raw TEXT[],
  methane_ppm DECIMAL,
  methane_percent DECIMAL,
  methane_temperature DECIMAL,
  methane_faults TEXT[]
);
```

## 🔍 Logging & Monitoring

### Log Files

- **sensor_payloads.log**: All received sensor data in JSON format
- **Console Output**: Real-time logging for development

### Log Format

```
2025-08-31 14:30:45,123 [INFO] {"timestamp": "2025-08-31T14:30:45+02:00", "ph": 14.2, ...}
```

### Monitoring Features

- **Supabase Upload Status**: Success/error logging
- **Temperature Validation**: Persistence decisions
- **CRC Validation**: Methane sensor integrity
- **Fault Detection**: Subsystem error analysis

## 🚀 Deployment

### Development

```bash
# With auto-reload
uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

### Production

```bash
# Standard deployment
python main.py

# With Gunicorn (recommended)
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5000
```

### Docker (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "main.py"]
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase project URL | - |
| `SUPABASE_KEY` | Supabase anon key | - |
| `LOG_LEVEL` | Logging level | INFO |
| `PORT` | Server port | 5000 |

### Advanced Configuration

```python
# Customizable constants in main.py
UPLOAD_INTERVAL = 10  # Supabase upload interval (seconds)
TEMP_MIN = 15.0      # Minimum valid temperature
TEMP_MAX = 50.0      # Maximum valid temperature
PH_OFFSET = 9        # pH calibration offset
```

# General Information

## 🤝 Contributors

- **Tim Siebert** - Lead Developer
- **Max Zboralski** - Co-Developer

## 📄 License

This project is private and intended for internal use.

## 🆘 Support

For questions or issues:

1. **Check logs**: `tail -f sensor_payloads.log`
2. **API documentation**: http://localhost:5000/docs
3. **Create issues**: In the repository
4. **Contact development team**

---

**Version**: 2.0.0  
**Last Updated**: August 31, 2025  
**Python**: 3.8+  
**Framework**: FastAPI
