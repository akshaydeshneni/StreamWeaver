# Use a Python 3.9 image as the base
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the producer script
COPY main.py .

# Command to run the producer
CMD ["python", "main.py"]
