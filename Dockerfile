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

# START_MODE controls which bot(s) to run:
#   all        — Run both Atlas and Donna in the same process (default, production)
#   atlas      — Run Atlas (news agent) only
#   secretary  — Run Donna (calendar secretary) only
ARG START_MODE=all
ENV START_MODE=${START_MODE}

CMD ["sh", "-c", "python scripts/run_${START_MODE}.py"]
