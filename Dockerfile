FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# (none required unless you add pydub/ffmpeg for OGG voice conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure runtime directories exist
RUN mkdir -p logs

CMD ["python", "scripts/run_bot.py"]
