FROM python:3.8-slim

WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
COPY /data/coffee.db /data/coffee.db
RUN chmod 777 /app/data/moviescollections.db
EXPOSE 3000
CMD ["python", "app.py"]