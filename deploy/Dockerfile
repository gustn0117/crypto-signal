FROM docker:cli

RUN apk add --no-cache git python3

COPY webhook.py /webhook.py

WORKDIR /repo

CMD ["python3", "/webhook.py"]
