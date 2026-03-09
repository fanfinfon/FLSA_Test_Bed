"""
General Purpose:
This script continuously reads JSON payloads from connected Arduino devices via USB.
It dynamically assigns each Arduino a 23-register Modbus Slave Databank based on its 'sensor_id'.
- Register 0 explicitly holds the sensor_id.
- Registers 1-21 hold the remaining telemetry.
- Register 22 is polled continuously; if the Master writes a command (>0) to it, it is sent as a raw binary byte back to the Arduino.
Selected routing/network fields are intercepted and forwarded to the FL system via process_fl_data.
"""

import serial
import json
import threading
import time
import glob
from pymodbus.server.sync import StartTcpServer
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext
)

# --- Configuration ---
BAUD_RATE = 115200
MODBUS_PORT = 502
MASTER_CMD_REG = 22

# --- Global Modbus Context (The Dictionary Bypass) ---
# It is critical that this dictionary remains at the global level!
slaves_dict = {} 
context = ModbusServerContext(slaves=slaves_dict, single=False)
context_lock = threading.Lock()

# Fields expressly extracted for the Federated Learning processing.
FL_FIELDS = {
    "mac", "ip.src_host", "ip.dst_host", 
    "tcp.srcport", "tcp.dstport", "tcp.len", 
    "mbtcp.trans_id", "mbtcp.len"
}

def process_fl_data(fl_payload):
    """
    Hook for passing intercepted routing data to the Federated Learning model.
    """
    pass

def init_databank_if_needed(target_sensor_id):
    """
    If the Master hasn't registered a databank for this sensor_id yet, we create it.
    """
    global slaves_dict # Explicitly tell Python to use the global dictionary
    
    with context_lock:
        # We check our custom dictionary directly, bypassing the broken library method
        if target_sensor_id not in slaves_dict:
            print(f"[*] Initializing new Modbus Databank for sensor_id: {target_sensor_id}")
            
            # MEMORY BUFFER: We allocate 100 registers instead of 23. 
            # This completely eliminates any possibility of native "Index out of bounds" memory errors.
            new_slave = ModbusSlaveContext(
                hr=ModbusSequentialDataBlock(0, [0] * 100),
                zero_mode=True 
            )
            
            # Map the slave directly into our custom dictionary
            slaves_dict[target_sensor_id] = new_slave


def serial_reader_thread(port_name):
    global slaves_dict # Explicitly tell Python to use the global dictionary
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1)
        print(f"Connected to Arduino on {port_name}")
    except Exception as e:
        print(f"Error opening serial port {port_name}: {e}")
        return

    while True:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                if not line:
                    continue
                
                # Parse Arduino JSON payload
                data = json.loads(line)
                
                # 'sensor_id' is the universal identifier now (e.g., Integer 1)
                s_id = data.get("sensor_id", 1)
                try:
                    s_id = int(s_id)
                except ValueError:
                    s_id = 1
                
                # Ensure the Modbus Server knows about this sensor_id
                init_databank_if_needed(s_id)
                
                fl_payload = {}
                telemetry_values = []
                
                # Split payload
                for key, value in data.items():
                    if key in FL_FIELDS:
                        fl_payload[key] = value
                    elif key != "sensor_id": # Ignore sensor_id for linear mapping, it is forced to Reg 0
                        # Try to cast to int (scale floats by 100)
                        if isinstance(value, float):
                            telemetry_values.append(int(value * 100))
                        elif isinstance(value, int):
                            telemetry_values.append(value)
                        else:
                            try:
                                telemetry_values.append(int(float(value)))
                            except:
                                telemetry_values.append(0)
                
                # Forward routing metrics
                process_fl_data(fl_payload)
                
                # Update Modbus Holding Registers safely via our custom dictionary
                with context_lock:
                    if s_id in slaves_dict:
                        slave = slaves_dict[s_id]  # Explicit dict lookup
                        # Set register 0 static to the sensor id
                        slave.setValues(3, 0, [s_id])
                        
                        # Populate sequential registers from 1 onward
                        for pointer, val in enumerate(telemetry_values):
                            hr_index = pointer + 1
                            # Prevent overwriting the command register 22
                            if hr_index < MASTER_CMD_REG:
                                slave.setValues(3, hr_index, [val])
                                
            except json.JSONDecodeError:
                pass # skip garbage text on serial
            except Exception as e:
                print(f"Exception parsing payload on {port_name}: {e}")
        
        # Continuously poll the databank's Command Register (22) for Master interactions
        try:
            if 's_id' in locals():
                with context_lock:
                    if s_id in slaves_dict:
                        slave = slaves_dict[s_id]
                        # Read 1 value from Holding Register [3], index 22
                        master_cmd = slave.getValues(3, MASTER_CMD_REG, 1)[0]
                        
                        # If a command > 0 exists, immediately send it to the Arduino and clear register
                        if master_cmd > 0:
                            ser.write((str(master_cmd) + '\n').encode('utf-8'))
                            # Clear register to 0 to prevent infinite command looping
                            slave.setValues(3, MASTER_CMD_REG, [0])
        except Exception as e:
            # Added a print statement here to catch any future mapping errors quietly
            print(f"Master Polling Error on {port_name}: {e}")
            pass

        time.sleep(0.01)

def run_modbus_server():
    """Starts the synchronous TCP Slave process using pymodbus"""
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'Tubitak Project Node'
    identity.ProductCode = 'RPi3-Modbus-Slave'
    identity.ModelName = 'Grid Simulation Slave Node'

    print(f"Starting dynamic Modbus TCP Slave Server on port {MODBUS_PORT}...")
    StartTcpServer(context=context, identity=identity, address=("0.0.0.0", MODBUS_PORT))

if __name__ == "__main__":
    usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    
    if not usb_ports:
        print("No Arduinos detected via USB. Please attach devices.")
    
    # Launch concurrent listeners for each connected USB path
    for port in usb_ports:
        t = threading.Thread(target=serial_reader_thread, args=(port,), daemon=True)
        t.start()
        
    # Kick off Modbus Server
    run_modbus_server()