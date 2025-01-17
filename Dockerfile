FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apk add --no-cache git

COPY requirements.txt .

RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY . .

CMD ["python", "main.py"]
