#include <math.h>

// --- PINS ---
const int GREEN_LED_PIN = 2;
const int RED_LED_PIN = 3;

int dummy_value = 12;

// --- SENSOR IDENTIFICATION ---
// Change these for EACH physical Arduino you program!
int sensor_id = 32;                    // Device 1, Device 2, Device 3...
String ip_src_host = "192.168.137.75"; // Simulate a unique IP for this sensor
String mac_address = "f6:eb:b4:19:b3:8e"; // Simulate a unique MAC

// --- NETWORK CONSTANTS ---
String ip_dst_host = "192.168.137.9"; // SCADA Server (RPi-1)
int tcp_dstport = 502;                // Modbus standard port
int mbtcp_len = 6;                    // Fixed length for standard Modbus query
int tcp_len = 64;                     // Fixed TCP packet size
unsigned int mbtcp_trans_id = 0;

// --- STATE VARIABLES ---
int current_state = 1;

void setup() {
  Serial.begin(115200);

  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);

  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);

  randomSeed(analogRead(0));
}

void loop() {

  // 1. check incoming serial data
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "1") {
      digitalWrite(GREEN_LED_PIN, HIGH);
      digitalWrite(RED_LED_PIN, LOW);
      current_state = 1;
    } else if (command == "2") {
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, HIGH);
      current_state = 2;
    }
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
  payload += "\"current_state\":" + String(current_state) + ",";
  payload += "\"dummy_value\":" + String(dummy_value);
  payload += "}";

  // Send the data over USB/Serial
  Serial.println(payload);

  delay(300); // 100ms update rate
}