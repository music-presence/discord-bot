FROM python:3.12

WORKDIR /
ADD requirements.txt .
RUN pip install -r requirements.txt
ADD bot.py .
ADD objects ./objects
ADD enums ./enums
ADD utils ./utils

VOLUME [ "/data" ]
WORKDIR /data

CMD ["python", "-u", "/bot.py"] 
