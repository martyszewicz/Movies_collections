FROM python:3.9

WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
RUN pip install requests
COPY templates /app/templates
COPY /data/moviescollections.db /data/moviescollections.db
RUN chmod 777 /app/data/moviescollections.db
EXPOSE 3000
CMD ["python", "app.py"]