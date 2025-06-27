# Use the official Python base image
FROM python:3.12-slim-bullseye

# Install system dependencies and Microsoft ODBC driver in a single layer
# IMPORTANT: Use lib64 for the driver path on 64-bit systems
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    unixodbc-dev \
    # Add other build-essential dependencies if needed for your packages
    gcc \
    g++ \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    # Clean up APT cache to reduce image size
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configure dynamic linker with the CORRECT path (lib64)
RUN echo "/opt/microsoft/msodbcsql17/lib64" > /etc/ld.so.conf.d/mssql-driver.conf && ldconfig

# Set up ODBC driver configuration with the CORRECT path (lib64)
RUN printf "[ODBC Driver 17 for SQL Server]\nDescription=Microsoft ODBC Driver 17 for SQL Server\nDriver=/opt/microsoft/msodbcsql17/lib64/libmsodbcsql-17.so\n" > /etc/odbcinst.ini

# Set up app environment
WORKDIR /app

# Copy and install Python dependencies (this order optimizes caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose app port
EXPOSE 10000

# Run app using Gunicorn + Uvicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:10000"]
