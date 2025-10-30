FROM python:3.11-slim

# Create user with sudo privileges
RUN apt-get update && apt-get --no-install-recommends install -y sudo=1.9.16p2-3 && \
    useradd -m -s /bin/bash appuser && \
    echo "appuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["opentelemetry-instrument", "python", "supervisor_function.py"]
