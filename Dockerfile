FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitoring_bot.py .

CMD ["python", "monitoring_bot.py"]
