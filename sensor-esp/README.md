# Smart Biodigester Monitor - ESP32 Firmware

> Production-ready ESP32 firmware for multi-sensor biodigester monitoring with real-time data transmission

## 📋 Overview

The Smart Biodigester ESP32 firmware is a sophisticated, production-ready solution for monitoring biogas fermenters. It integrates multiple sensor types for comprehensive data collection and transmits measurements in real-time to a FastAPI backend.

### 🎯 Key Features

- **Multi-Sensor Integration**: pH, temperature, environmental, and methane sensors
- **Real-time Data Transmission**: HTTP POST every 2 seconds to FastAPI backend
- **INIR2 Protocol Support**: Specialized methane sensor communication
- **Robust Error Handling**: WiFi reconnection and sensor validation
- **Production-Ready Architecture**: Modular code with comprehensive documentation

### 🔬 Supported Sensors

- **pH Sensor**: DFRobot Gravity V2 (0-14 pH, ±0.1 accuracy)
- **Temperature Sensors**: Up to 2x DS18B20 (±0.5°C accuracy)
- **Environmental Sensor**: BME680 (temperature, humidity, pressure, gas)
- **Methane Sensor**: INIR2-ME100 (0-100% LEL with CRC validation)

## Hardware Requirements

### ESP32 Development Board
- **Model**: ESP32-WROOM-32 or compatible
- **Flash**: Minimum 4MB
- **RAM**: Minimum 520KB
- **WiFi**: 2.4GHz 802.11 b/g/n

### Pin Assignment

| Sensor | Pin | Type | Description |
|--------|-----|------|-------------|
| pH Sensor | G35 | Analog | ADC1_CH7 (0-3.3V) |
| Temperature Sensors | G4 | Digital | 1-Wire Bus |
| BME680 SDA | G21 | I2C | I2C Data Line |
| BME680 SCL | G22 | I2C | I2C Clock Line |
| INIR2 TX | G17 | UART | ESP TX → Sensor RX |
| INIR2 RX | G16 | UART | ESP RX ← Sensor TX |

### Power Supply
- **Operating Voltage**: 5V/1A recommended
- **Power Consumption**: ~240mA (active with WiFi)
- **Voltage Regulator**: Integrated (3.3V for sensors)

## Installation and Setup

### Prerequisites

- **Arduino IDE**: Version 2.0+ or PlatformIO
- **ESP32 Board Package**: espressif/arduino-esp32
- **Libraries**: See dependencies below

### 1. Arduino IDE Configuration

```bash
# Add Board Manager URL:
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json

# Select Board:
ESP32 Dev Module
```

### 2. Required Libraries

```cpp
// Install via Arduino Library Manager:
DFRobot_ESP_PH          // pH sensor library
OneWire                 // 1-Wire communication
DallasTemperature       // DS18B20 temperature sensors
Adafruit_BME680         // BME680 environmental sensor
ArduinoJson             // JSON serialization
```

### 3. Configuration Setup

```cpp
// Adjust WiFi credentials in esp.ino:
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";
const char* backend_url = "https://your-domain.com/data";
```

### 4. Hardware Wiring

#### pH Sensor (DFRobot V2)
```
VCC → 5V
GND → GND
Signal → G35
```

#### DS18B20 Temperature Sensors
```
VCC → 3.3V
GND → GND
Data → G4 (with 4.7kΩ pull-up resistor)
```

#### BME680 Environmental Sensor
```
VCC → 3.3V
GND → GND
SDA → G21
SCL → G22
```

#### INIR2 Methane Sensor
```
VCC → 5V (separate power supply recommended)
GND → GND
TX → G16 (ESP RX)
RX → G17 (ESP TX)
```

### 5. Upload and Testing

```bash
# 1. Compile and upload code
# 2. Open Serial Monitor (115200 baud)
# 3. Check WiFi connection and sensor initialization
# 4. Verify data transmission to backend
```

## 📡 Data Transmission

### JSON Payload Format

```json
{
  "ph": 6.8,
  "ph_voltage": 2150.5,
  "temp1": 35.2,
  "temp2": 34.8,
  "bme_temperature": 22.1,
  "bme_humidity": 65.3,
  "bme_pressure": 1013.25,
  "bme_gas_resistance": 45.2,
  "methan_raw": [
    "0000005b",
    "00001234",
    "0000aaaa",
    "00000bb8",
    "12345678",
    "87654321",
    "0000005d"
  ]
}
```

### Transmission Parameters

- **Interval**: 2 seconds
- **Protocol**: HTTP POST
- **Content-Type**: application/json
- **Timeout**: 10 seconds
- **Retry Logic**: Automatic reconnection

## 🔍 Debugging and Monitoring

### Serial Monitor Output

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                     SENSOR READINGS                               ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ pH Value:            6.85                                        ┃
┃ pH Voltage:        2150.5 mV                                     ┃
┃ Temperature 1:       35.2 °C  (Sensor 1)                        ┃
┃ Temperature 2:       34.8 °C  (Sensor 2)                        ┃
┣━━━━━━━━━━━━━━━ BME680 (Air) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ Temp.:               22.1 °C                                     ┃
┃ Humidity:            65.3 % RH                                   ┃
┃ Pressure:          1013.25 hPa                                   ┃
┃ Gas resistance:      45.2 kΩ                                     ┃
┣━━━━━━━━━━━━━━━ Methane Sensor RAW (UART) ━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ 0000005b                                                         ┃
┃ 00001234                                                         ┃
┃ 0000aaaa ...                                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## 🤝 Contributors

- **Tim Siebert** - Lead Developer, Hardware Integration
- **Max Zboralski** - Co-Developer, Software Architecture

## 📄 License

This project is private and intended for internal use.

## 🆘 Support

For questions or issues:

1. **Check Serial Monitor**: Analyze debugging output
2. **Hardware Wiring**: Verify pin assignments and voltages
3. **WiFi Connection**: Validate network configuration
4. **Backend Integration**: Check API endpoint and payload format
5. **Create Issues**: Document in repository
6. **Contact Development Team**

---

**Version**: 1.0.0  
**Last Updated**: August 31, 2025  
**Hardware**: ESP32-WROOM-32  
**Framework**: Arduino Core for ESP32
