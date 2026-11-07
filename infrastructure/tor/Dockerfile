FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ENV DEBIAN_FRONTEND=noninteractive
COPY debian-snapshot.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update -o Acquire::Retries=3 -o APT::Update::Error-Mode=any \
 && apt-get install -y --no-install-recommends \
      tor=0.4.9.15-0+deb13u1 ca-certificates=20250419+deb13u1 zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
 && rm -rf /var/lib/apt/lists/*
COPY torrc /etc/tor/torrc
USER debian-tor
EXPOSE 9050
CMD ["tor", "-f", "/etc/tor/torrc"]
