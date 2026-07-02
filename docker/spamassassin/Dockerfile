FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends spamassassin spamc spamd ca-certificates gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/despamizer-spamassassin-entrypoint
RUN chmod +x /usr/local/bin/despamizer-spamassassin-entrypoint

EXPOSE 783

CMD ["/usr/local/bin/despamizer-spamassassin-entrypoint"]
