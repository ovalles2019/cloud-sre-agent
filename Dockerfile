FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV DEMO_MODE=true
ENV PYTHONPATH=/app

EXPOSE 8080
CMD ["python", "app.py"]
