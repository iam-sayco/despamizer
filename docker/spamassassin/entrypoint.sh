#!/bin/sh
set -eu

spamassassin_rules_version() {
    spamassassin --version | awk '
        /^SpamAssassin version / {
            split($3, version, ".")
            printf "%d.%06d\n", version[1], version[2] * 1000 + version[3]
        }
    '
}

ensure_rules_exist() {
    rules_dir="/var/lib/spamassassin/$(spamassassin_rules_version)"
    mkdir -p "$rules_dir"

    if ! find "$rules_dir" -type f -name '*.cf' -print -quit | grep -q .; then
        cp -a /usr/share/spamassassin/. "$rules_dir"/
    fi
}

update_rules_loop() {
    while true; do
        update_rules
        sleep "${SA_UPDATE_INTERVAL_SECONDS:-86400}"
    done
}

update_rules() {
    sa-update || true
    chown -R debian-spamd:debian-spamd /var/lib/spamassassin
}

ensure_rules_exist
update_rules
update_rules_loop &

exec /usr/sbin/spamd \
    --create-prefs \
    --username=debian-spamd \
    --max-children "${SPAMD_MAX_CHILDREN:-2}" \
    --helper-home-dir=/var/lib/spamassassin \
    --listen=0.0.0.0 \
    --port=783 \
    --allowed-ips=0.0.0.0/0 \
    --allow-tell \
    --syslog=stderr
