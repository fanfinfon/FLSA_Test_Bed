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
REGISTER_COUNT = 23
MASTER_CMD_REG = 22 # Modbus maps indices starting at 0, so Register 22 is the 23rd index.

# --- Global Modbus Context ---
# We initialize an empty layout. As Arduinos connect, we will add ModbusSlaveContexts
# keyed by their parsed 'sensor_id'.
context = ModbusServerContext(slaves={}, single=False)
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
    If the Master hasn't registered a databank for this sensor_id yet, we create a
    block of 23 Modbus holding registers (hr) initialized to 0.
    """
    with context_lock:
        if target_sensor_id not in context.slaves():
            print(f"[*] Initializing new 23-register Modbus Databank for sensor_id: {target_sensor_id}")
            # Create the 23-register block
            new_slave = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * REGISTER_COUNT))
            
            # Register it into the server context dict
            if hasattr(context, 'store'):
                context.store[target_sensor_id] = new_slave
            else:
                # Older pymodbus fallback
                context.slaves()[target_sensor_id] = new_slave

def serial_reader_thread(port_name):
    """
    Worker thread assigned to one USB port. It reads JSON continuously, categorizes it,
    writes the telemetry into its respective ModbusSlaveContext, and checks Register 22
    for outgoing binary commands.
    """
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
                
                # Update Modbus Holding Registers safely
                with context_lock:
                    if s_id in context.slaves():
                        slave = context[s_id]
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
                    if s_id in context.slaves():
                        slave = context[s_id]
                        # Read 1 value from Holding Register [3], index 22
                        master_cmd = slave.getValues(3, MASTER_CMD_REG, 1)[0]
                        
                        # If a command > 0 exists, immediately send it to the Arduino and clear register
                        if master_cmd > 0:
                            ser.write((str(master_cmd) + '\n').encode('utf-8'))
                            # Clear register to 0 to prevent infinite command looping
                            slave.setValues(3, MASTER_CMD_REG, [0])
        except Exception:
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