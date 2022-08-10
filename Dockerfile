FROM python:3.8-slim-buster

WORKDIR /usr/src/app
COPY . /usr/src/app/
RUN pip3 install -r requirements.txt

CMD ["python3", "-u", "main.py"]
