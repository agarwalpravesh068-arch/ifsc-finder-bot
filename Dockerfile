# ✅ Stable Python version use करो
FROM python:3.10-slim

# Working directory
WORKDIR /app

# Dependencies copy
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code copy
COPY . .

# Expose port for Render
EXPOSE 10000

# Run bot
CMD ["python", "telegram_ifsc_bot.py"]
