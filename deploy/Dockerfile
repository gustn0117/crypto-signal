FROM docker:cli

RUN apk add --no-cache git python3 \
    && git config --global --add safe.directory /repo

COPY webhook.py /webhook.py

WORKDIR /repo

CMD ["python3", "/webhook.py"]
