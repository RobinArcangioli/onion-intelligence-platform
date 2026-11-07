FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc
ENV DEBIAN_FRONTEND=noninteractive
COPY debian-snapshot.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update -o Acquire::Retries=3 -o APT::Update::Error-Mode=any \
 && apt-get install -y --no-install-recommends tor=0.4.9.11-0+deb12u1 ca-certificates=20250419~deb12u2 \
 && rm -rf /var/lib/apt/lists/*
COPY torrc /etc/tor/torrc
USER debian-tor
EXPOSE 9050
CMD ["tor", "-f", "/etc/tor/torrc"]
