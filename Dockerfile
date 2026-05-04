# Use a slim version of Python for a smaller image size
FROM python:3.10-slim

# Set environment variables to prevent Python from writing .pyc files 
# and to ensure output is sent straight to terminal (unbuffered)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
# gcc, libssl, and libffi are required for building Paramiko/Cryptography
# iputils-ping is needed for the Health Check (ICMP) logic
RUN apt-get update && apt-get install -y \
    gcc \
    libssl-dev \
    libffi-dev \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY ./app .

# Note: No CMD here because it's defined in docker-compose.yml 
# to distinguish between the API and the Worker roles.
