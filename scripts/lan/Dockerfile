FROM python:3.13-alpine
RUN apk add --no-cache openssl \
    && pip install --no-cache-dir qrcode==8.2 zeroconf==0.148.0 ifaddr==0.2.0
WORKDIR /tools
COPY civia_lan.py ./
ENTRYPOINT ["python", "/tools/civia_lan.py"]
