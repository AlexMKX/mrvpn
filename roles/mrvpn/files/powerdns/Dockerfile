FROM alpine:latest

#ENV LUA_VERSION 5.1

RUN apk update
#
#RUN apk add lua${LUA_VERSION}
#RUN apk add lua${LUA_VERSION}-dev

RUN apk add bash build-base curl git openssl unzip wget lua5.3-http

RUN apk add --no-cache \
    pdns-recursor \
    py3-pip \
    python3


RUN pip3 install --no-cache-dir 'Jinja2<3.1' envtpl

RUN mkdir -p /etc/pdns/api.d \
  && chown -R recursor: /etc/pdns/api.d \
  && mkdir -p /var/run/pdns-recursor \
  && chown -R recursor: /var/run/pdns-recursor

ENV VERSION=4.5 \
  PDNS_setuid=recursor \
  PDNS_setgid=recursor \
  PDNS_daemon=no

EXPOSE 53 53/udp

COPY recursor.conf.tpl /
COPY docker-entrypoint.sh /
COPY interceptor.lua /
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT [ "/docker-entrypoint.sh" ]

CMD [ "/usr/sbin/pdns_recursor" ]