# ✅ Python 3.11 का stable version (telegram-bot compatible)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# System dependencies (pandas, numpy etc. को support करने के लिए)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Start command
CMD ["python", "telegram_ifsc_bot.py"]
