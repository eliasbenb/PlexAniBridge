FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache git

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
