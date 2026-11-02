FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# APP_JSON 由 docker-compose 注入（挂载仓库根 apps.json 为可读写）
ENV APP_JSON=/data/apps.json
ENV FLASK_APP=app.py

EXPOSE 5000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
