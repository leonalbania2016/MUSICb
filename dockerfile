# Use official Python
FROM python:3.11-slim

# Install system deps and ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app

# Copy requirements
COPY requirements.txt /app/requirements.txt

# Install python deps
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy bot
COPY bot.py /app/bot.py

# Expose port for Render health check (same as port our Flask will bind)
ENV PORT=10000
EXPOSE 10000

# Start the bot (Render expects a web process so container listens on $PORT)
CMD ["python", "bot.py"]
