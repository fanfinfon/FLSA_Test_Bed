# Use a slim Python image to keep the container small and fast
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install the required Python libraries
RUN pip install --no-cache-dir pymodbus pyserial

# Copy the Python script into the container
COPY gateway.py .

# Expose the standard Modbus TCP port
EXPOSE 502

# Run the script with unbuffered output (-u) so prints show up immediately in Docker logs
CMD ["python", "-u", "RPİ-3_Modbus.py"]