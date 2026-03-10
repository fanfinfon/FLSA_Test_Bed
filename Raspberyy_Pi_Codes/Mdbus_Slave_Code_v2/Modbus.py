"""
General Purpose:
This script continuously reads JSON payloads from connected Arduino devices via USB.
It dynamically assigns each Arduino a 23-register Modbus Slave Databank based on its 'sensor_id'.
- Register 0 explicitly holds the sensor_id.
- Registers 1-21 hold the remaining telemetry.
- Register 22 is polled continuously; if the Master writes a command (>0) to it,
  it is sent as an ASCII command back to the Arduino.

Selected routing/network fields are intercepted and forwarded to the FL system via process_fl_data.

Requires: pymodbus==3.6.9, pyserial
"""

import serial
import json
import threading
import time
import glob
import asyncio

from pymodbus.server import StartAsyncTcpServer
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)

# --- Configuration ---
BAUD_RATE = 115200
MODBUS_PORT = 502
MASTER_CMD_REG = 22

# --- Global Modbus Context ---
slaves_dict = {}
context = ModbusServerContext(slaves=slaves_dict, single=False)
context_lock = threading.Lock()

# Fields extracted for Federated Learning processing
FL_FIELDS = {
    "mac", "ip.src_host", "ip.dst_host",
    "tcp.srcport", "tcp.dstport", "tcp.len",
    "mbtcp.trans_id", "mbtcp.len"
}


def process_fl_data(fl_payload):
    """Hook for passing intercepted routing data to the Federated Learning model."""
    pass


def init_databank_if_needed(target_sensor_id):
    """Create a Modbus databank for this sensor_id if one doesn't exist yet."""
    with context_lock:
        if target_sensor_id not in slaves_dict:
            print(f"[*] Initializing new Modbus Databank for sensor_id: {target_sensor_id}")
            new_slave = ModbusSlaveContext(
                hr=ModbusSequentialDataBlock(0, [0] * 100),
                zero_mode=True
            )
            slaves_dict[target_sensor_id] = new_slave


def serial_reader_thread(port_name):
    """Reads JSON from an Arduino over USB serial and writes to Modbus holding registers."""
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1)
        print(f"Connected to Arduino on {port_name}")
    except Exception as e:
        print(f"Error opening serial port {port_name}: {e}")
        return

    s_id = None
    json_errors = 0

    while True:
        # --- Read and parse incoming serial data ---
        s_id = None  # Reset each iteration to prevent stale ID usage in command polling
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                if not line:
                    pass
                else:
                    data = json.loads(line)

                    # Extract sensor_id (integer key for slave routing)
                    s_id = data.get("sensor_id", 1)
                    try:
                        s_id = int(s_id)
                    except (ValueError, TypeError):
                        s_id = 1

                    init_databank_if_needed(s_id)

                    fl_payload = {}
                    telemetry_values = []

                    # Split payload into FL fields and telemetry registers
                    for key, value in data.items():
                        if key in FL_FIELDS:
                            fl_payload[key] = value
                        elif key != "sensor_id":
                            if isinstance(value, float):
                                telemetry_values.append(int(value * 100))
                            elif isinstance(value, int):
                                telemetry_values.append(value)
                            else:
                                try:
                                    telemetry_values.append(int(float(value)))
                                except Exception:
                                    telemetry_values.append(0)

                    process_fl_data(fl_payload)

                    # Write to Modbus holding registers
                    with context_lock:
                        if s_id in slaves_dict:
                            slave = slaves_dict[s_id]
                            slave.setValues(3, 0, [s_id])  # Reg 0 = sensor_id

                            for pointer, val in enumerate(telemetry_values):
                                hr_index = pointer + 1
                                if hr_index < MASTER_CMD_REG:
                                    slave.setValues(3, hr_index, [val])
                                else:
                                    print(f"[WARN] Telemetry overflow on sensor {s_id}: "
                                          f"field at index {pointer} exceeds max register {MASTER_CMD_REG - 1}")
                                    break

                            print(f"[Modbus Bank {s_id}] Reg 0: [{s_id}] | "
                                  f"Regs 1-{len(telemetry_values)}: {telemetry_values}")

            except json.JSONDecodeError:
                json_errors += 1
                if json_errors % 20 == 0:
                    print(f"[WARN] {port_name}: {json_errors} malformed JSON lines dropped")
            except Exception as e:
                print(f"Exception parsing payload on {port_name}: {e}")

        # --- Poll command register 22 for Master commands ---
        if s_id is not None:
            try:
                with context_lock:
                    if s_id in slaves_dict:
                        slave = slaves_dict[s_id]
                        master_cmd = slave.getValues(3, MASTER_CMD_REG, 1)[0]
                        if master_cmd > 0:
                            # Send ASCII command string to Arduino (e.g., "1\n" or "2\n")
                            ser.write((str(master_cmd) + '\n').encode('utf-8'))
                            slave.setValues(3, MASTER_CMD_REG, [0])  # Clear to prevent looping
            except Exception as e:
                print(f"Master Polling Error on {port_name}: {e}")

        time.sleep(0.05)  # 50ms loop — fast enough to catch all 300ms Arduino packets


async def run_modbus_server():
    """Starts the async Modbus TCP server (pymodbus 3.x)."""
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'Tubitak Project Node'
    identity.ProductCode = 'RPi3-Modbus-Slave'
    identity.ModelName = 'Grid Simulation Slave Node'

    print(f"Starting async Modbus TCP Slave Server on port {MODBUS_PORT}...")
    await StartAsyncTcpServer(
        context=context,
        identity=identity,
        address=("0.0.0.0", MODBUS_PORT)
    )


if __name__ == "__main__":
    usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')

    if not usb_ports:
        print("No Arduinos detected via USB. Please attach devices.")

    # Launch a serial reader thread for each connected Arduino
    for port in usb_ports:
        t = threading.Thread(target=serial_reader_thread, args=(port,), daemon=True)
        t.start()

    # Run the async Modbus server on the main thread's event loop
    asyncio.run(run_modbus_server())