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

# 1. Initialize Multiple Modbus Datastores (One for each Arduino Unit ID)
# We pre-create memory banks for Unit IDs 1, 2, 3, and 4. You can add more if needed.
slaves = {
    1: ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*10)),
    2: ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*10)),
    3: ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*10)),
    4: ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*10))
}

# single=False is crucial here! It tells the server to respect the Unit ID requested by Node-RED.
context = ModbusServerContext(slaves=slaves, single=False)

def process_fl_data(data_dict):
    """
    This is where your Federated Learning model will hook in.
    """
    pass

def serial_reader_thread(port_name):
    """
    This thread constantly reads a specific USB port.
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
                
                data = json.loads(line)
                
                # Extract routing data
                unit_id = int(data.get('mbtcp.unit_id', 1)) # Default to 1 if missing
                sensor_name = data.get('sensor_id', 'Unknown_Sensor')
                
                # Separate the data
                voltage = data.pop('voltage', 0.0) 
                fl_network_data = data             
                
                # Send to FL pipeline
                process_fl_data(fl_network_data)
                
                # Update the SPECIFIC Modbus Register for this Unit ID
                if unit_id in slaves:
                    voltage_int = int(voltage * 100) 
                    
                    # Grab the correct memory bank for this specific Arduino
                    slave_context = context[unit_id]
                    slave_context.setValues(3, 0, [voltage_int])
                    
                    print(f"[Port: {port_name}] Sensor: {sensor_name} (Unit ID: {unit_id}) | Voltage: {voltage}V -> Modbus Int: {voltage_int}")
                else:
                    print(f"Warning: Received data for unconfigured Unit ID {unit_id}")
                
            except json.JSONDecodeError:
                pass # Ignore malformed serial lines
            except Exception as e:
                print(f"Error reading data on {port_name}: {e}")
        
        time.sleep(0.01)

def run_modbus_server():
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'Tubitak Project Node'
    identity.ProductCode = 'RPi3-Gateway'
    identity.ModelName = 'Grid Simulation Slave Node'

    print(f"Starting Modbus TCP Server on port {MODBUS_PORT}...")
    StartTcpServer(context=context, identity=identity, address=("0.0.0.0", MODBUS_PORT))

if __name__ == "__main__":
    # 2. Automatically find all connected Arduinos (ttyUSB0, ttyUSB1, etc.)
    usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    
    if not usb_ports:
        print("No Arduinos detected. Please check your USB connections.")
    
    # Start a separate listening thread for EVERY Arduino plugged in
    for port in usb_ports:
        thread = threading.Thread(target=serial_reader_thread, args=(port,), daemon=True)
        thread.start()
    
    # Start the Modbus server
    run_modbus_server()