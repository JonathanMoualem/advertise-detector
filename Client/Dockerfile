FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY Client/requirements-web.txt /app/Client/requirements-web.txt
RUN pip install --no-cache-dir -r /app/Client/requirements-web.txt

COPY Alerting /app/Alerting
COPY Client /app/Client

ENV PYTHONPATH=/app
ENV FLASK_APP=Client.web_server

EXPOSE 8080

CMD ["python", "-m", "Client.web_server"]
