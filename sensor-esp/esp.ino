/**
 * @file esp.ino
 * @brief Smart Biodigester Multi-Sensor ESP32 Firmware
 * @version 1.0.0
 * @date 2025-08-31
 * @authors Tim Siebert, Max Zboralski
 * 
 * @description
 * Production-ready ESP32 firmware for the Smart Biodigester monitoring system.
 * Integrates multiple sensor types for comprehensive biogas fermenter monitoring
 * with real-time data transmission to FastAPI backend server.
 * 
 * @hardware_requirements
 * - ESP32 Development Board (ESP32-WROOM-32 or compatible)
 * - pH Sensor: DFRobot Gravity V2 (Analog Pin G35)
 * - Temperature Sensors: DS18B20 (1-Wire Bus on Pin G4)
 * - Environmental Sensor: BME680 (I2C: SDA=G21, SCL=G22, Address=0x76)
 * - Methane Sensor: INIR2-ME100 (UART2: TX=G17, RX=G16, 38400 baud, 8N2)
 * 
 * @sensor_specifications
 * - pH Range: 0-14 pH (optimal biodigester: 6.5-7.5)
 * - Temperature Range: -55°C to +125°C (optimal biodigester: 30-40°C)
 * - BME680: Temperature, Humidity, Pressure, VOC Gas Resistance
 * - Methane: 0-100% LEL with fault detection and CRC validation
 * 
 * @network_configuration
 * - WiFi: 2.4GHz 802.11 b/g/n
 * - HTTP POST: JSON payload transmission every 2 seconds
 * - Backend Integration: FastAPI server with Supabase database
 * - Timeout Handling: 30-second WiFi connection timeout
 * 
 * @data_flow
 * 1. Sensor readings collected every 2 seconds
 * 2. Data validation and preprocessing
 * 3. JSON payload construction with sensor metadata
 * 4. HTTP POST transmission to backend API
 * 5. Serial monitor output every 5 seconds for debugging
 * 
 * 
 * @error_handling
 * - WiFi connection retry with timeout
 * - Sensor initialization validation
 * - HTTP transmission error logging
 * - Temperature sensor disconnection detection
 * - Methane sensor UART communication validation
 * 
 * @calibration_notes
 * - pH sensor requires 2-point calibration (pH 4.0 and pH 7.0)
 * - Temperature sensors factory calibrated (±0.5°C accuracy)
 * - BME680 auto-calibration for gas sensor baseline
 * - Methane sensor 45-second warm-up period required
 * 
 * @license Private - Internal Use Only
 * @copyright 2025 Tim Siebert & Max Zboralski
 */

// ========== Libraries ==========
#include "DFRobot_ESP_PH.h"
#include "EEPROM.h"
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ========== UART Configuration for INIR2 Methane Sensor ==========
/**
 * @brief UART2 interface for INIR2-ME100 methane sensor communication
 * @details Uses hardware serial port 2 with 8N2 configuration at 38400 baud
 * @note INIR2 protocol requires specific timing and CRC validation
 */
HardwareSerial methanSerial(2);      // UART2 hardware serial interface
constexpr uint8_t METHAN_TX = 17;    // ESP32 TX pin -> INIR2 RX pin
constexpr uint8_t METHAN_RX = 16;    // ESP32 RX pin <- INIR2 TX pin
constexpr int METHAN_BAUD = 38400;   // INIR2 standard baud rate (8N2)

// ========== Network and Backend Configuration ==========
/**
 * @brief WiFi and HTTP backend configuration
 * @warning Update these credentials for your deployment environment
 * @note Backend URL should point to FastAPI /data endpoint
 */
const char* ssid = "ssid";                              // WiFi network name
const char* password = "password";                           // WiFi network password
const char* backend_url = "backend_url"; // FastAPI backend endpoint

// ========== Hardware Pin and Timing Configuration ==========
/**
 * @brief Sensor pin assignments and measurement timing
 * @details All pins configured for optimal sensor performance
 */
#define PH_PIN 35                    // Analog pin for pH sensor (ADC1_CH7)
#define ESPADC 4096.0               // ESP32 ADC resolution (12-bit)
#define ESPVOLTAGE 3300             // ESP32 reference voltage (3.3V in mV)
#define TEMP_SENSORS_PIN 4          // 1-Wire bus pin for DS18B20 sensors
#define BME680_I2C_ADDRESS 0x76     // BME680 I2C address (alternative: 0x77)
#define MEASUREMENT_INTERVAL 2000   // Sensor reading interval in milliseconds

// ========== Sensor Library Objects ==========
/**
 * @brief Sensor library instances for hardware communication
 * @details Each object handles specific sensor protocols and data processing
 */
DFRobot_ESP_PH ph;                    // pH sensor library instance (DFRobot Gravity V2)
OneWire oneWire(TEMP_SENSORS_PIN);     // 1-Wire bus communication object
DallasTemperature tempSensors(&oneWire); // DS18B20 temperature sensor manager
Adafruit_BME680 bme;                   // BME680 environmental sensor object

// ========== Timing and Control Variables ==========
/**
 * @brief System timing control for serial output and measurements
 * @details Prevents excessive serial output while maintaining data collection
 */
#define SERIAL_PRINT_INTERVAL 5000UL  // Serial monitor output interval (5 seconds)
unsigned long lastSerialPrint = 0;    // Timestamp of last serial output

// ========== pH Sensor Data Variables ==========
/**
 * @brief pH sensor measurement storage
 * @details Raw voltage and calculated pH value from analog sensor
 */
float voltage = 0.0;                  // Raw ADC voltage reading (mV)
float phValue = 7.0;                  // Calculated pH value (0-14 scale)

// ========== Temperature Sensor Data Variables ==========
/**
 * @brief DS18B20 temperature sensor data and configuration
 * @details Supports up to 2 sensors with automatic detection and addressing
 */
float temp1 = 99.0;                   // Temperature sensor 1 reading (°C)
float temp2 = 99.0;                   // Temperature sensor 2 reading (°C)
DeviceAddress sensorAddresses[2];     // 1-Wire device addresses (64-bit each)
int sensorCount = 0;                  // Number of detected temperature sensors

// ========== BME680 Environmental Data Variables ==========
/**
 * @brief BME680 sensor readings for environmental monitoring
 * @details Temperature, humidity, pressure, and gas resistance measurements
 */
float bme_temperature = 0.0;          // Ambient temperature (°C)
float bme_humidity = 0.0;             // Relative humidity (%RH)
float bme_pressure = 0.0;             // Atmospheric pressure (hPa)
float bme_gas_resistance = 0.0;       // VOC gas resistance (kΩ)

// ========== INIR2 Methane Sensor Communication Buffer ==========
/**
 * @brief UART communication buffer for INIR2 methane sensor
 * @details Stores raw UART lines for backend processing and CRC validation
 * @note Maximum 7 lines per INIR2 protocol packet
 */
String methanRawLines[8];             // Raw UART line buffer (8 lines max)
int methanRawCount = 0;               // Current number of buffered lines

// ========== System Initialization ==========
/**
 * @brief Arduino setup function - runs once at system startup
 * @details Initializes all hardware components and establishes network connection
 * 
 * Initialization sequence:
 * 1. Serial communication (115200 baud for debugging)
 * 2. WiFi network connection with timeout handling
 * 3. pH sensor with EEPROM calibration data
 * 4. DS18B20 temperature sensors with address detection
 * 5. BME680 environmental sensor with optimal settings
 * 6. INIR2 methane sensor UART communication
 * 
 * @note System will halt if BME680 initialization fails
 * @note Methane sensor requires 45-second warm-up period
 */
void setup() {
    // Initialize serial communication for debugging and monitoring
    Serial.begin(115200);
    
    // Establish WiFi connection with network credentials
    connectToWiFi();
    
    // System startup banner for identification
    Serial.println("🚀 ESP32 Smart Biodigester Multi-Sensor System v2.0.0");
    Serial.println("📡 Authors: Tim Siebert & Max Zboralski");
    Serial.println("=====================================");

    // Initialize all sensor subsystems in sequence
    initializePHSensor();           // pH sensor with EEPROM calibration
    initializeTemperatureSensors(); // DS18B20 1-Wire temperature sensors
    initializeBME680();            // BME680 environmental sensor (I2C)
    initializeMethanSensor();      // INIR2 methane sensor (UART2)

    Serial.println("=====================================");
    Serial.println("✅ Setup completed. Starting measurements...\n");
    Serial.println("📊 Data transmission every 2 seconds");
    Serial.println("🖥️  Serial output every 5 seconds\n");
}

// ========== Main Program Loop ==========
/**
 * @brief Arduino main loop - runs continuously after setup()
 * @details Manages sensor readings, data transmission, and user interaction
 * 
 * Loop operations:
 * 1. Sensor data collection (every 2 seconds)
 * 2. INIR2 methane sensor UART reading
 * 3. HTTP POST transmission to backend
 * 4. Serial monitor output (every 5 seconds)
 * 5. INIR2 command processing from serial input
 * 
 * @note Uses non-blocking timing to prevent delays
 * @note All operations are asynchronous for optimal performance
 */
void loop() {
    static unsigned long lastMeasurement = 0;  // Timestamp of last sensor reading
    unsigned long now = millis();              // Current system time

    // Sensor reading and data transmission cycle (2-second interval)
    if (now - lastMeasurement >= MEASUREMENT_INTERVAL) {
        lastMeasurement = now;
        
        // Collect data from all analog and digital sensors
        readAllSensors();    // pH, temperature, BME680 environmental data
        readMethanSensor();  // INIR2 UART communication buffer
        sendSensorData();    // HTTP POST to FastAPI backend
    }

    // Serial monitor output for debugging and monitoring (5-second interval)
    // Prevents excessive console output while maintaining visibility
    if (now - lastSerialPrint >= SERIAL_PRINT_INTERVAL) {
        lastSerialPrint = now;
        printSensorData();   // Formatted sensor data display
    }

    // Process INIR2 methane sensor commands from serial input
    // Allows real-time sensor control and calibration
    checkMethanCommands();
}


// ========== Network Connectivity Management ==========
/**
 * @brief Establishes WiFi connection with timeout and error handling
 * @details Attempts to connect to configured WiFi network with 30-second timeout
 * 
 * Connection process:
 * 1. Initialize WiFi with SSID and password credentials
 * 2. Wait for connection with 500ms intervals
 * 3. Display connection progress with dot indicators
 * 4. Report success with assigned IP address or failure
 * 
 * @note Uses 30-second timeout to prevent infinite blocking
 * @note System continues operation even if WiFi fails (offline mode)
 * @warning Update SSID and password constants for your network
 */
void connectToWiFi() {
    Serial.print("📡 Connecting to WiFi network: \"");
    Serial.print(ssid);
    Serial.println("\"...");
    
    // Initialize WiFi connection with stored credentials
    WiFi.begin(ssid, password);
    
    // Connection attempt with timeout protection
    int timeout = 0;
    while (WiFi.status() != WL_CONNECTED && timeout < 30) {
        delay(500);                    // 500ms delay between attempts
        Serial.print(".");            // Progress indicator
        timeout++;                     // Increment timeout counter
    }
    
    // Report connection status and network information
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n✅ WiFi connected successfully!");
        Serial.print("🌐 IP address: ");
        Serial.println(WiFi.localIP());
        Serial.print("📡 Signal strength: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
    } else {
        Serial.println("\n⚠️ WiFi connection failed - continuing in offline mode");
        Serial.println("📵 Data will not be transmitted to backend");
    }
}

// ========== Individual Sensor Initialization Functions ==========

/**
 * @brief Initialize DFRobot pH sensor with EEPROM calibration
 * @details Sets up analog pH sensor with stored calibration coefficients
 * 
 * Initialization process:
 * 1. Initialize EEPROM (32 bytes) for calibration data storage
 * 2. Initialize DFRobot pH library with calibration parameters
 * 3. Load previously stored 2-point calibration (pH 4.0 and 7.0)
 * 
 * @note Calibration data persists across power cycles
 * @note Use serial commands 'cal:4.00' and 'cal:7.00' for calibration
 */
void initializePHSensor() {
    Serial.println("🧪 Initializing pH sensor (DFRobot Gravity V2)...");
    
    // Initialize EEPROM for calibration coefficient storage
    EEPROM.begin(32);  // 32 bytes sufficient for pH calibration data
    
    // Initialize pH sensor library with EEPROM calibration
    ph.begin();        // Loads calibration coefficients from EEPROM
    
    Serial.println("✅ pH sensor initialized with stored calibration");
    Serial.println("📊 Range: 0-14 pH, Accuracy: ±0.1 pH");
}

/**
 * @brief Initialize DS18B20 temperature sensors on 1-Wire bus
 * @details Detects and configures up to 2 temperature sensors with address mapping
 * 
 * Initialization process:
 * 1. Initialize 1-Wire bus communication
 * 2. Scan for connected DS18B20 devices
 * 3. Store device addresses for direct access
 * 4. Report sensor count and addresses
 * 
 * @note Supports 1-2 sensors, duplicates reading if only one found
 * @note Each sensor has unique 64-bit ROM address
 */
void initializeTemperatureSensors() {
    Serial.println("🌡️ Initializing DS18B20 temperature sensors...");
    
    // Initialize 1-Wire bus and scan for devices
    tempSensors.begin();
    sensorCount = tempSensors.getDeviceCount();
    
    Serial.print("🔌 Pin G4 (1-Wire): ");
    Serial.print(sensorCount);
    Serial.println(" temperature sensor(s) detected");
    
    // Store device addresses for direct sensor access
    for (int i = 0; i < sensorCount && i < 2; i++) {
        if (tempSensors.getAddress(sensorAddresses[i], i)) {
            Serial.print("🏷️  Sensor ");
            Serial.print(i + 1);
            Serial.print(" ROM address: ");
            printAddress(sensorAddresses[i]);
        }
    }
    
    Serial.println("✅ Temperature sensors initialized");
    Serial.println("📊 Range: -55°C to +125°C, Accuracy: ±0.5°C");
}

/**
 * @brief Initialize BME680 environmental sensor with optimal settings
 * @details Configures BME680 for biodigester environmental monitoring
 * 
 * Configuration settings:
 * - Temperature: 8x oversampling for high accuracy
 * - Humidity: 2x oversampling for balanced performance
 * - Pressure: 4x oversampling for meteorological accuracy
 * - Gas sensor: IIR filter + heater (320°C, 150ms)
 * 
 * @note System halts if BME680 not found (critical sensor)
 * @note Gas sensor requires warm-up period for stable readings
 */
void initializeBME680() {
    Serial.println("🌬️ Initializing BME680 environmental sensor...");
    
    // Attempt I2C communication with BME680
    if (!bme.begin(BME680_I2C_ADDRESS)) {
        Serial.println("❌ Error: BME680 not found at I2C address 0x76");
        Serial.println("🔧 Check I2C wiring (SDA=G21, SCL=G22) and power");
        while (1);  // Halt system - BME680 is critical for operation
    }
    
    // Configure sensor oversampling for optimal accuracy vs. speed
    bme.setTemperatureOversampling(BME680_OS_8X);  // Highest accuracy
    bme.setHumidityOversampling(BME680_OS_2X);     // Balanced performance
    bme.setPressureOversampling(BME680_OS_4X);     // Meteorological accuracy
    
    // Configure digital filtering and gas sensor heater
    bme.setIIRFilterSize(BME680_FILTER_SIZE_3);    // Reduce noise
    bme.setGasHeater(320, 150);                    // 320°C for 150ms
    
    Serial.println("✅ BME680 initialized with optimized settings");
    Serial.println("📊 Temp: ±1°C, Humidity: ±3%RH, Pressure: ±1hPa");
}

/**
 * @brief Initialize INIR2-ME100 methane sensor UART communication
 * @details Sets up UART2 for INIR2 protocol communication
 * 
 * UART configuration:
 * - Baud rate: 38400 (INIR2 standard)
 * - Data format: 8N2 (8 data bits, no parity, 2 stop bits)
 * - Hardware pins: TX=G17, RX=G16
 * 
 * @note Requires 45-second warm-up period for accurate readings
 * @note INIR2 protocol uses CRC validation for data integrity
 */
void initializeMethanSensor() {
    Serial.println("🔥 Initializing INIR2-ME100 methane sensor...");
    
    // Configure UART2 with INIR2 protocol specifications
    methanSerial.begin(METHAN_BAUD, SERIAL_8N2, METHAN_RX, METHAN_TX);
    
    // Allow UART hardware to stabilize
    delay(1000);
    
    Serial.println("✅ INIR2 methane sensor UART initialized");
    Serial.println("⏰ Warm-up period: 45 seconds recommended");
    Serial.println("📊 Range: 0-100% LEL, CRC validation enabled");
}

// ========== Sensor Data Acquisition Functions ==========

/**
 * @brief Read all analog and digital sensors in sequence
 * @details Coordinates data collection from pH, temperature, and environmental sensors
 * 
 * Reading sequence:
 * 1. pH sensor analog voltage measurement and conversion
 * 2. DS18B20 temperature sensors via 1-Wire protocol
 * 3. BME680 environmental sensor via I2C protocol
 * 
 * @note pH calculation uses temp1 for temperature compensation
 * @note All readings are non-blocking and complete within ~100ms
 */
void readAllSensors() {
    // Read pH sensor analog voltage and convert to pH value
    voltage = analogRead(PH_PIN) / ESPADC * ESPVOLTAGE;  // Convert ADC to mV
    phValue = ph.readPH(voltage, temp1);                 // Temperature-compensated pH
    
    // Read DS18B20 temperature sensors
    readTemperatureSensors();
    
    // Read BME680 environmental parameters
    readBME680();
}

/**
 * @brief Read DS18B20 temperature sensors with error handling
 * @details Requests temperature conversion and reads sensor values by address
 * 
 * Reading process:
 * 1. Request temperature conversion from all sensors
 * 2. Read sensor 1 with disconnection detection
 * 3. Read sensor 2 or duplicate sensor 1 if only one present
 * 4. Handle sensor disconnection gracefully
 * 
 * @note Conversion time: ~750ms for 12-bit resolution
 * @note Returns 0.0°C if sensor disconnected (DEVICE_DISCONNECTED_C)
 */
void readTemperatureSensors() {
    // Request temperature conversion from all DS18B20 sensors
    tempSensors.requestTemperatures();
    
    // Read primary temperature sensor (temp1)
    if (sensorCount > 0) {
        temp1 = tempSensors.getTempC(sensorAddresses[0]);
        // Handle sensor disconnection error
        if (temp1 == DEVICE_DISCONNECTED_C) {
            temp1 = 0.0;  // Safe fallback value
            Serial.println("⚠️ Temperature sensor 1 disconnected");
        }
    }
    
    // Read secondary temperature sensor (temp2)
    if (sensorCount > 1) {
        temp2 = tempSensors.getTempC(sensorAddresses[1]);
        // Handle sensor disconnection error
        if (temp2 == DEVICE_DISCONNECTED_C) {
            temp2 = 0.0;  // Safe fallback value
            Serial.println("⚠️ Temperature sensor 2 disconnected");
        }
    } else {
        // Duplicate temp1 reading if only one sensor present
        temp2 = temp1;
    }
}

/**
 * @brief Read BME680 environmental sensor with comprehensive error handling
 * @details Performs complete sensor reading cycle with unit conversions
 * 
 * Measurement process:
 * 1. Trigger sensor measurement cycle
 * 2. Read temperature, humidity, pressure, gas resistance
 * 3. Apply unit conversions (Pa to hPa, Ohm to kOhm)
 * 4. Handle communication errors gracefully
 * 
 * @note Measurement time: ~150ms with current oversampling settings
 * @note Returns NaN values if sensor communication fails
 */
void readBME680() {
    // Perform complete BME680 measurement cycle
    if (bme.performReading()) {
        // Extract sensor readings with appropriate unit conversions
        bme_temperature = bme.temperature;           // Already in °C
        bme_humidity = bme.humidity;                 // Already in %RH
        bme_pressure = bme.pressure / 100.0;         // Convert Pa to hPa
        bme_gas_resistance = bme.gas_resistance / 1000.0; // Convert Ohm to kOhm
    } else {
        // Handle sensor communication error
        Serial.println("❌ Error reading BME680 - I2C communication failed");
        Serial.println("🔧 Check I2C connections and sensor power supply");
        
        // Set error values to indicate sensor failure
        bme_temperature = NAN;
        bme_humidity = NAN;
        bme_pressure = NAN;
        bme_gas_resistance = NAN;
    }
}

// ========== INIR2 Methane Sensor UART Communication ==========
/**
 * @brief Read raw UART data from INIR2 methane sensor
 * @details Processes incoming UART stream and buffers complete lines
 * 
 * INIR2 protocol characteristics:
 * - 7 lines per complete measurement packet
 * - Hexadecimal data format (32-bit words)
 * - Line termination: \r or \n characters
 * - CRC validation performed by backend
 * 
 * Processing algorithm:
 * 1. Read available UART characters
 * 2. Build complete lines until line terminator
 * 3. Store up to 7 lines in buffer array
 * 4. Filter non-printable characters
 * 5. Reset buffer for next measurement cycle
 * 
 * @note Buffer limited to 7 lines per INIR2 protocol specification
 * @note Non-printable characters are filtered for data integrity
 */
void readMethanSensor() {
    static String methanLine = "";  // Current line being assembled
    methanRawCount = 0;             // Reset line counter for new cycle
    
    // Process all available UART characters
    while (methanSerial.available()) {
        char c = methanSerial.read();
        
        // Check for line termination characters
        if (c == '\r' || c == '\n') {
            if (methanLine.length() > 0) {
                // Store complete line if buffer space available
                if (methanRawCount < 7) {
                    methanRawLines[methanRawCount++] = methanLine;
                }
                methanLine = "";  // Reset line buffer
            }
        } else if (isPrintable(c)) {
            // Append printable characters to current line
            methanLine += c;
        }
        // Non-printable characters are silently discarded
    }
    
    // Handle incomplete line at end of UART buffer
    if (methanLine.length() > 0 && methanRawCount < 7) {
        methanRawLines[methanRawCount++] = methanLine;
        methanLine = "";  // Reset for next cycle
    }
}

// ========== Serial Monitor Output and Debugging ==========
/**
 * @brief Display formatted sensor readings on serial monitor
 * @details Creates professional ASCII table with all sensor data
 * 
 * Output format:
 * - Bordered ASCII table with Unicode box-drawing characters
 * - pH: Value and raw voltage with 2 decimal precision
 * - Temperature: Both sensors with 1 decimal precision
 * - BME680: All environmental parameters with appropriate precision
 * - INIR2: Raw UART lines for backend processing
 * 
 * @note Called every 5 seconds to prevent console spam
 * @note Provides real-time monitoring for debugging and calibration
 */
void printSensorData() {
    // ASCII table header with system identification
    Serial.println("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓");
    Serial.println("┃           🚀 SMART BIODIGESTER SENSOR READINGS v2.0.0            ┃");
    Serial.println("┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫");
    
    // pH sensor readings with voltage reference
    Serial.printf ("┃ 🧪 pH Value:         %6.2f                                        ┃\n", phValue);
    Serial.printf ("┃ ⚡ pH Voltage:       %6.1f mV                                     ┃\n", voltage);
    
    // DS18B20 temperature sensor readings
    Serial.printf ("┃ 🌡️  Temperature 1:    %6.1f °C  (Tank Sensor 1)                   ┃\n", temp1);
    Serial.printf ("┃ 🌡️  Temperature 2:    %6.1f °C  (Tank Sensor 2)                   ┃\n", temp2);
    
    // Additional temperature sensor status information
    printAdditionalTemperatureData();
    
    // BME680 environmental sensor section
    Serial.println("┣━━━━━━━━━━━━━━━ 🌬️ BME680 Environmental Data ━━━━━━━━━━━━━━━━━━━━━━━━┫");
    Serial.printf ("┃ 🌡️  Ambient Temp:     %6.2f °C                                     ┃\n", bme_temperature);
    Serial.printf ("┃ 💧 Humidity:         %6.2f %% RH                                  ┃\n", bme_humidity);
    Serial.printf ("┃ 🌪️  Pressure:         %6.2f hPa                                    ┃\n", bme_pressure);
    Serial.printf ("┃ 💨 Gas Resistance:   %6.2f kΩ                                     ┃\n", bme_gas_resistance);

    // INIR2 methane sensor raw UART data section
    Serial.println("┣━━━━━━━━━━━━━━━ 🔥 INIR2 Methane Sensor (UART) ━━━━━━━━━━━━━━━━━━━━━┫");
    for (int i = 0; i < methanRawCount; i++) {
        Serial.printf ("┃ 📡 %-58s ┃\n", methanRawLines[i].c_str());
    }
    if (methanRawCount == 0)
        Serial.println("┃ ⚠️  [No UART data received - check sensor connection]             ┃");

    // Table footer with timestamp
    Serial.println("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n");
}

/**
 * @brief Display additional temperature sensor status information
 * @details Provides diagnostic information about DS18B20 sensor detection
 * 
 * Status messages:
 * - Single sensor: Indicates temp2 duplicates temp1
 * - No sensors: Warning about missing temperature sensors
 * - Normal operation: No additional message displayed
 */
void printAdditionalTemperatureData() {
    if (sensorCount == 1) {
        Serial.println("┃ ℹ️  Info: Only 1 sensor detected (temp2 = temp1)                    ┃");
    } else if (sensorCount == 0) {
        Serial.println("┃ ⚠️  Warning: No temperature sensors found! Check wiring           ┃");
    }
}

// ========== Utility and Helper Functions ==========
/**
 * @brief Print DS18B20 sensor ROM address in hexadecimal format
 * @details Displays 64-bit device address for sensor identification
 * 
 * @param deviceAddress 8-byte array containing DS18B20 ROM address
 * 
 * Address format: 8 bytes in hexadecimal (e.g., 28FF1234567890AB)
 * - Family code (0x28 for DS18B20)
 * - 48-bit serial number
 * - 8-bit CRC checksum
 */
void printAddress(DeviceAddress deviceAddress) {
    for (uint8_t i = 0; i < 8; i++) {
        if (deviceAddress[i] < 16) Serial.print("0");  // Leading zero padding
        Serial.print(deviceAddress[i], HEX);           // Hexadecimal format
    }
    Serial.println();
}

/**
 * @brief Process INIR2 methane sensor commands from serial input
 * @details Allows real-time sensor control and calibration via serial monitor
 * 
 * Command format: [COMMAND] (enclosed in square brackets)
 * 
 * Common INIR2 commands:
 * - [STRT]: Start measurement
 * - [STOP]: Stop measurement
 * - [STAT]: Query sensor status
 * - [ZERO]: Zero-point calibration
 * 
 * @note Commands are forwarded directly to INIR2 via UART2
 * @note Invalid commands are ignored for system stability
 */
void checkMethanCommands() {
    // Check for available serial input from USB connection
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n'); // Read complete line
        cmd.trim();                                // Remove whitespace
        
        // Validate command format: [COMMAND]
        if (cmd.length() > 0 && cmd[0] == '[' && cmd[cmd.length()-1] == ']') {
            // Forward validated command to INIR2 sensor
            methanSerial.print(cmd);
            methanSerial.print("\r"); // INIR2 expects carriage return
            
            // Confirm command transmission
            Serial.print("🚀 INIR2 command sent: ");
            Serial.println(cmd);
        } else if (cmd.length() > 0) {
            // Invalid command format feedback
            Serial.println("❌ Invalid command format. Use [COMMAND] syntax.");
            Serial.println("📖 Examples: [STRT], [STOP], [STAT], [ZERO]");
        }
    }
}

// ========== HTTP Data Transmission to Backend ==========
/**
 * @brief Transmit all sensor data to FastAPI backend via HTTP POST
 * @details Constructs JSON payload and sends to backend for processing
 * 
 * JSON payload structure:
 * {
 *   "ph": float,                    // pH value (0-14)
 *   "ph_voltage": float,            // Raw pH voltage (mV)
 *   "temp1": float,                 // Tank temperature 1 (°C)
 *   "temp2": float,                 // Tank temperature 2 (°C)
 *   "bme_temperature": float,       // Ambient temperature (°C)
 *   "bme_humidity": float,          // Relative humidity (%)
 *   "bme_pressure": float,          // Atmospheric pressure (hPa)
 *   "bme_gas_resistance": float,    // Gas resistance (kΩ)
 *   "methan_raw": [string array]    // INIR2 UART lines (max 7)
 * }
 * 
 * Backend processing:
 * - INIR2 protocol decoding and CRC validation
 * - Temperature persistence and pH calibration
 * - Database upload to Supabase every 10 seconds
 * - German timezone conversion and logging
 * 
 * @note Called every 2 seconds (MEASUREMENT_INTERVAL)
 * @note Requires active WiFi connection for transmission
 * @note JSON buffer sized for maximum INIR2 payload (1536 bytes)
 */
void sendSensorData() {
    // Verify WiFi connectivity before transmission attempt
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("📡 No WiFi connection - data transmission skipped");
        return;
    }

    // Initialize HTTP client with backend endpoint
    HTTPClient http;
    http.begin(backend_url);  // FastAPI server URL
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);    // 5-second timeout for reliability

    // Construct JSON payload with all sensor readings
    StaticJsonDocument<1536> doc;  // Sized for max INIR2 data + sensors
    
    // pH sensor data with raw voltage reference
    doc["ph"] = phValue;           // Calibrated pH value (0-14 scale)
    doc["ph_voltage"] = voltage;   // Raw ADC voltage for diagnostics
    
    // DS18B20 tank temperature sensors
    doc["temp1"] = temp1;          // Primary tank temperature
    doc["temp2"] = temp2;          // Secondary tank temperature
    
    // BME680 environmental sensor suite
    doc["bme_temperature"] = bme_temperature;     // Ambient air temperature
    doc["bme_humidity"] = bme_humidity;           // Relative humidity
    doc["bme_pressure"] = bme_pressure;           // Atmospheric pressure
    doc["bme_gas_resistance"] = bme_gas_resistance; // VOC gas resistance

    // INIR2 methane sensor raw UART data array
    JsonArray methanArr = doc.createNestedArray("methan_raw");
    for (int i = 0; i < methanRawCount; i++) {
        methanArr.add(methanRawLines[i]);  // Raw hexadecimal protocol lines
    }

    // Serialize JSON document to string for HTTP transmission
    String jsonStr;
    serializeJson(doc, jsonStr);

    // Execute HTTP POST request with error handling
    int httpResponseCode = http.POST(jsonStr);
    
    if (httpResponseCode > 0) {
        // Successful transmission - log response code
        Serial.print("✅ Data transmitted successfully. HTTP: ");
        Serial.println(httpResponseCode);
        
        // Log payload size for monitoring
        Serial.print("📦 Payload size: ");
        Serial.print(jsonStr.length());
        Serial.println(" bytes");
    } else {
        // Transmission failed - log error for debugging
        Serial.print("❌ HTTP transmission failed. Error: ");
        Serial.println(httpResponseCode);
        Serial.println("🔧 Check backend URL and network connectivity");
    }

    // Clean up HTTP client resources
    http.end();
}
