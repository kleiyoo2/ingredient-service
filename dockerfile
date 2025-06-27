# Use official slim Python image
FROM python:3.12-slim-bullseye

# Step 1: Install system & build dependencies, and ODBC support
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

# Step 2: Find the real path of libmsodbcsql-17.so
RUN echo "--- 🔍 Searching for libmsodbcsql-17.so ---" \
    && find / -name "libmsodbcsql-17.so" > /driver_path.txt || echo "Driver not found" \
    && cat /driver_path.txt

# Step 3: Set the correct dynamic linker path based on find result (assuming lib64)
RUN echo "/opt/microsoft/msodbcsql17/lib64" > /etc/ld.so.conf.d/mssql-driver.conf && ldconfig

# Step 4: Write ODBC config to point to the driver
RUN printf "[ODBC Driver 17 for SQL Server]\nDescription=Microsoft ODBC Driver 17 for SQL Server\nDriver=/opt/microsoft/msodbcsql17/lib64/libmsodbcsql-17.so\n" > /etc/odbcinst.ini

# Step 5: Debug installed drivers and paths
RUN echo "--- ✅ ODBC Driver Check ---" \
    && cat /etc/odbcinst.ini \
    && echo "--- ✅ ldconfig -p | grep msodbc ---" \
    && ldconfig -p | grep msodbc || echo "Driver not found in ld cache" \
    && echo "--- ✅ odbcinst -q -d ---" \
    && odbcinst -q -d

# Step 6: Set working directory and install app dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Step 7: Copy all source files
COPY . .

# Step 8: Expose the port (change if needed)
EXPOSE 10000

# Step 9: Run FastAPI using Gunicorn + Uvicorn worker
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:10000"]
