# Use the official Python base image
FROM python:3.12-slim-bullseye

# Install system dependencies and Microsoft ODBC driver
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    gcc \
    g++ \
    unixodbc \
    unixodbc-dev \
    libpq-dev \
    libsasl2-dev \
    libssl-dev \
    libffi-dev \
    libodbc1 \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17

# Configure dynamic linker with correct path
RUN echo "/opt/microsoft/msodbcsql17/lib" > /etc/ld.so.conf.d/mssql-driver.conf && ldconfig

# Set up ODBC driver configuration
RUN printf "[ODBC Driver 17 for SQL Server]\nDescription=Microsoft ODBC Driver 17 for SQL Server\nDriver=/opt/microsoft/msodbcsql17/lib/libmsodbcsql-17.so\n" > /etc/odbcinst.ini

# Diagnostic (optional – remove in production)
RUN echo "--- Checking actual driver path ---" \
    && find / -name "libmsodbcsql-17.so" || echo "Driver not found"

# Clean APT cache (after everything to avoid removing needed files)
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up app environment
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy app code
COPY . .

# Expose app port
EXPOSE 10000

# Run app using Gunicorn + Uvicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:10000"]
