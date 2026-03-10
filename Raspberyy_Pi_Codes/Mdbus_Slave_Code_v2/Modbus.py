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

--- KEY ARCHITECTURE FIX (v3) ---
pymodbus 3.x runs StartAsyncTcpServer on the asyncio event loop (main thread).
Serial reader threads run on OS threads.

ROOT CAUSE OF TIMEOUT BUG:
  threading.Lock() blocks the entire asyncio event loop when held by a serial thread.
  Every incoming Modbus TCP request from Node-RED froze until the lock released,
  causing consistent "Timed out" errors even though the TCP connection was open.

SECOND BUG:
  Mutating slaves_dict AFTER ModbusServerContext is created in pymodbus 3.x
  does not register new slaves with the live server — they are invisible to
  incoming requests.

SOLUTION:
  1. ALL slaves are pre-registered in KNOWN_SENSOR_IDS before the server starts.
  2. Serial threads only write register VALUES — never touch slaves_dict structure.
  3. threading.Lock removed entirely. CPython's GIL makes individual list-item
     writes atomic. Each port owns exactly one slave so there are no concurrent
     writes to the same registers between threads.
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
BAUD_RATE      = 115200
MODBUS_PORT    = 502
MASTER_CMD_REG = 22

# --- Pre-register ALL known sensor IDs here ---
# Add every sensor_id your Arduinos can report.
# The server must know about them at startup — pymodbus 3.x does not support
# adding slaves to the context after StartAsyncTcpServer begins.
KNOWN_SENSOR_IDS = [31, 32]   # <-- add more IDs here as you add Arduinos

def _make_slave():
    return ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * 100),
        zero_mode=True
    )

slaves_dict = {sid: _make_slave() for sid in KNOWN_SENSOR_IDS}
context = ModbusServerContext(slaves=slaves_dict, single=False)

# Fields extracted for Federated Learning processing
FL_FIELDS = {
    "mac", "ip.src_host", "ip.dst_host",
    "tcp.srcport", "tcp.dstport", "tcp.len",
    "mbtcp.trans_id", "mbtcp.len"
}


def process_fl_data(fl_payload):
    """Hook for passing intercepted routing data to the Federated Learning model."""
    pass


def serial_reader_thread(port_name):
    """
    Reads JSON from an Arduino over USB serial and writes values into
    the pre-registered Modbus holding registers.

    NO threading.Lock is used — see architecture note at top of file.
    Each thread owns exactly one slave (identified by sensor_id), so there
    are no concurrent writes to the same registers between threads.
    """
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1)
        print(f"[Serial] Connected to Arduino on {port_name}")
    except Exception as e:
        print(f"[Serial] Error opening {port_name}: {e}")
        return

    s_id = None
    json_errors = 0

    while True:
        s_id = None  # reset every iteration — prevents stale ID in command polling

        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                if not line:
                    pass
                else:
                    data = json.loads(line)

                    # Resolve sensor_id
                    raw_id = data.get("sensor_id", None)
                    try:
                        s_id = int(raw_id)
                    except (ValueError, TypeError):
                        print(f"[WARN] {port_name}: unreadable sensor_id '{raw_id}', skipping")
                        s_id = None

                    if s_id is None or s_id not in slaves_dict:
                        if s_id is not None:
                            print(f"[WARN] sensor_id {s_id} not in KNOWN_SENSOR_IDS — "
                                  f"add it to the list and restart. Skipping.")
                        s_id = None
                    else:
                        fl_payload = {}
                        telemetry_values = []

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

                        # Write to pre-registered slave — no lock needed
                        slave = slaves_dict[s_id]
                        slave.setValues(3, 0, [s_id])  # Reg 0 = sensor_id

                        for pointer, val in enumerate(telemetry_values):
                            hr_index = pointer + 1
                            if hr_index < MASTER_CMD_REG:
                                slave.setValues(3, hr_index, [val])
                            else:
                                print(f"[WARN] sensor {s_id}: telemetry overflow at "
                                      f"field index {pointer}, max is {MASTER_CMD_REG - 1}")
                                break

                        print(f"[Bank {s_id}] Reg0={s_id} | "
                              f"Regs1-{len(telemetry_values)}: {telemetry_values}")

            except json.JSONDecodeError:
                json_errors += 1
                if json_errors % 20 == 0:
                    print(f"[WARN] {port_name}: {json_errors} malformed JSON packets dropped")
            except Exception as e:
                print(f"[ERROR] {port_name} parse exception: {e}")

        # Poll command register 22 for Master-written commands
        if s_id is not None:
            try:
                slave = slaves_dict[s_id]
                master_cmd = slave.getValues(3, MASTER_CMD_REG, 1)[0]
                if master_cmd > 0:
                    ser.write((str(master_cmd) + '\n').encode('utf-8'))
                    slave.setValues(3, MASTER_CMD_REG, [0])  # clear to prevent loop
                    print(f"[CMD] Sent command {master_cmd} to Arduino on {port_name}")
            except Exception as e:
                print(f"[ERROR] Command poll on {port_name}: {e}")

        time.sleep(0.05)  # 50ms — fast enough to catch all 300ms Arduino packets


async def run_modbus_server():
    """Starts the async Modbus TCP server (pymodbus 3.x)."""
    identity = ModbusDeviceIdentification()
    identity.VendorName  = 'Tubitak Project Node'
    identity.ProductCode = 'RPi3-Modbus-Slave'
    identity.ModelName   = 'Grid Simulation Slave Node'

    print(f"[Modbus] Starting async TCP server on 0.0.0.0:{MODBUS_PORT}")
    print(f"[Modbus] Registered slave IDs: {list(slaves_dict.keys())}")

    await StartAsyncTcpServer(
        context=context,
        identity=identity,
        address=("0.0.0.0", MODBUS_PORT)
    )


if __name__ == "__main__":
    usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')

    if not usb_ports:
        print("[WARN] No Arduinos detected. Server starts with zeroed registers.")

    for port in usb_ports:
        t = threading.Thread(target=serial_reader_thread, args=(port,), daemon=True)
        t.start()

    asyncio.run(run_modbus_server())