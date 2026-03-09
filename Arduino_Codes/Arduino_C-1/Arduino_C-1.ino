#include <math.h>

// --- SENSOR IDENTIFICATION ---
// Change these for EACH physical Arduino you program!
int sensor_id = 31;                    // Device 1, Device 2, Device 3...
String ip_src_host = "192.168.137.36"; // Simulate a unique IP for this sensor
String mac_address = "CC-E9-81-F3-8F-1A"; // Simulate a unique MAC

// --- NETWORK CONSTANTS ---
String ip_dst_host = "192.168.137.9"; // SCADA Server (RPi-1)
int tcp_dstport = 502;                // Modbus standard port
int mbtcp_len = 6;                    // Fixed length for standard Modbus query
int tcp_len = 64;                     // Fixed TCP packet size

unsigned int mbtcp_trans_id = 0;

// --- VOLTAGE PARAMETERS ---
float mean_voltage = 220.0;
float std_dev_voltage = 2.0;

// --- BUTTON & TIMING CONSTANTS ---
const int BUTTON_PIN = 2; // Connect button between Pin 2 and GND
unsigned long overrideStartTime = 0;
bool isVoltageOverridden = false;
const unsigned long OVERRIDE_DURATION = 10000; // 10 seconds in milliseconds

void setup() {
  Serial.begin(115200);
  
  // Set up the button pin with the internal pull-up resistor
  pinMode(BUTTON_PIN, INPUT_PULLUP); 
  
  randomSeed(analogRead(0));
}

void loop() {
  // --- CHECK BUTTON STATE ---
  // If button is pressed (LOW) and we aren't already overriding
  if (digitalRead(BUTTON_PIN) == LOW && !isVoltageOverridden) {
    isVoltageOverridden = true;
    overrideStartTime = millis(); // Record the exact time the anomaly started
  }

  // --- CHECK TIMER ---
  // If we are currently overriding, check if 10 seconds have passed
  if (isVoltageOverridden && (millis() - overrideStartTime >= OVERRIDE_DURATION)) {
    isVoltageOverridden = false; // Turn off the override and return to normal
  }

  // 1. Determine Voltage (Normal vs. Anomaly)
  float voltage;
  
  if (isVoltageOverridden) {
    voltage = 250.0; // Hardcoded anomaly voltage
  } else {
    // Generate normally distributed voltage
    float u1 = random(1, 10000) / 10000.0;
    float u2 = random(1, 10000) / 10000.0;
    float z0 = sqrt(-2.0 * log(u1)) * cos(2.0 * PI * u2);
    voltage = mean_voltage + (z0 * std_dev_voltage);
  }

  // 2. Generate randomized network properties (that normally vary)
  int tcp_srcport = random(50000, 60000);
  mbtcp_trans_id++;

  // 3. Construct JSON payload
  String payload = "{";
  payload += "\"mac\":\"" + mac_address + "\",";
  payload += "\"ip.src_host\":\"" + ip_src_host + "\",";
  payload += "\"ip.dst_host\":\"" + ip_dst_host + "\",";
  payload += "\"tcp.srcport\":" + String(tcp_srcport) + ",";
  payload += "\"tcp.dstport\":" + String(tcp_dstport) + ",";
  payload += "\"tcp.len\":" + String(tcp_len) + ",";
  payload += "\"mbtcp.trans_id\":" + String(mbtcp_trans_id) + ",";
  payload += "\"sensor_id\":" + String(sensor_id) + ",";
  payload += "\"mbtcp.len\":" + String(mbtcp_len) + ",";
  payload += "\"voltage\":" + String(voltage, 2);
  payload += "}";

  // Send the data over USB/Serial
  Serial.println(payload);

  delay(100); // 100ms update rate
}