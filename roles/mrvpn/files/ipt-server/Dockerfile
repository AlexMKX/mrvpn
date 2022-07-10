FROM alpine:latest
RUN apk update

RUN apk add --no-cache \
    py3-pip \
    python3 \
    iptables \
    sudo \
    nftables \
    websocat


RUN pip install websockets

COPY . .
ENTRYPOINT ["/usr/bin/python3","/ipt_server.py"]

