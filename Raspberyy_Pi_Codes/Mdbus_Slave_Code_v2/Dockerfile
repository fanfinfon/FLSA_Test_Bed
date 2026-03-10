FROM python:3.11-slim

WORKDIR /app

RUN pip3 install --no-cache-dir "pymodbus==3.6.9" pyserial

COPY Modbus.py .

EXPOSE 502

# Run as root to bind privileged port 502
USER root

CMD ["python", "-u", "Modbus.py"]