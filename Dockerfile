# ✅ Official Python 3.11 image use करो
FROM python:3.11-slim

# Working directory set करो
WORKDIR /app

# Dependencies install करने से पहले system update
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy बाकी का project
COPY . .

# Start the bot
CMD ["python", "telegram_ifsc_bot.py"]
