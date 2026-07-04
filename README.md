# Despamizer

Despamizer is a Docker Compose based IMAP worker that scans configured inbox folders, classifies messages with SpamAssassin and local mailbox rules, and moves spam to the configured spam folder.

It is intentionally conservative: inbox processing only moves messages from `inbox_folder` to `spam_folder` when they are classified as spam. Permanent deletion is limited to spam-folder retention cleanup.

## How It Works

The Compose stack runs two services:

- `despamizer`: Python worker that connects to IMAP mailboxes and applies mailbox policy.
- `spamassassin`: internal SpamAssassin `spamd` service used for automatic spam scoring and learning.

SpamAssassin is not exposed on the host. The worker reaches it through the private Compose network at `spamassassin:783`.

Each worker cycle:

- fetches messages from each configured inbox without marking them as seen,
- skips messages previously rescued from spam,
- applies whitelist, blacklist, regex rules, and SpamAssassin scoring,
- moves spam to the configured spam folder unless dry-run mode is enabled,
- scans spam folders for manual spam feedback,
- permanently deletes spam-folder messages older than mailbox retention when dry-run mode is disabled,
- records bounded local state in SQLite.

## Installation

Clone the repository:

```bash
git clone git@github.com:iam-sayco/despamizer.git
cd despamizer
```

Create local config files:

```bash
cp config.example.yaml config.yaml
cp .env.default .env
```

Edit `config.yaml` with your mailboxes. Keep `DESPAMIZER_WORKER_DRY_RUN=true` in `.env` for the first run.

Start the stack:

```bash
./install.sh
```

Inspect logs:

```bash
make logs
```

Changes in `config.yaml`, `.env`, and files under `despamizer/` are mounted into the container and are visible on the next run without rebuilding the image.

## Common Commands

Probe mailbox folders before choosing `inbox_folder` and `spam_folder`:

```bash
make probe MAILBOX=personal
```

After logs look correct, disable dry-run in `.env`:

```env
DESPAMIZER_WORKER_DRY_RUN=false
```

Restart the worker:

```bash
make restart
```

Run one worker cycle:

```bash
make run-once
```

Run one forced dry-run cycle:

```bash
make dry-run
```

Follow worker logs:

```bash
make logs
```

Stop the stack:

```bash
make stop
```

Rebuild after dependency or Dockerfile changes:

```bash
make rebuild
```

## Runtime Modes

Start the long-running worker:

```bash
docker compose up -d
```

Run one worker cycle and exit:

```bash
make run-once
```

Run one forced dry-run cycle and exit:

```bash
make dry-run
```

The long-running worker sleeps for `DESPAMIZER_WORKER_POLL_INTERVAL_SECONDS` between scans. The default interval is `300` seconds.

## Mailbox Config

Mailbox configuration lives in `config.yaml`. This file is ignored by git. Use `config.example.yaml` as the template.

```yaml
mailboxes:
  - name: personal
    host: imap.example.com
    port: 993
    username: user@example.com
    password: change-me
    inbox_folder: INBOX
    spam_folder: Junk
    retention: 30
    whitelist:
      senders:
        - trusted@example.com
      domains:
        - important-bank.example
    blacklist:
      senders:
        - scammer@example.net
      domains:
        - spam-domain.example
    rules:
      - type: sender
        pattern: "@bad-domain\\.example$"
        score: 10
      - type: subject
        pattern: "free money|crypto giveaway"
        score: 8
      - type: body
        pattern: "unsubscribe here"
        score: 2
```

Mailbox fields:

- `name`: local mailbox name used in logs and state.
- `host`, `port`, `username`, `password`: IMAP connection settings. Only encrypted IMAP is supported.
- `inbox_folder`: folder scanned by the worker.
- `spam_folder`: folder where spam is moved and manual spam feedback is read.
- `retention`: spam-folder retention in days before permanent deletion, default `30`.
- `whitelist.senders`: sender addresses that are never moved to spam.
- `whitelist.domains`: sender domains that are never moved to spam.
- `blacklist.senders`: sender addresses always treated as spam.
- `blacklist.domains`: sender domains always treated as spam.
- `rules`: extra regex scoring rules.

Rule types:

- `sender`: checks the sender header/address.
- `subject`: checks the subject.
- `body`: checks plain text and HTML body content.

Rules use Python regular expressions and are case-insensitive.

To discover exact IMAP folder names, define the mailbox connection fields first, then run:

```bash
make probe MAILBOX=personal
```

The command prints folder names from the remote IMAP server and does not fetch or move messages.

## Config File Security

`config.yaml` contains IMAP credentials and is ignored by git. Despamizer keeps it mounted read-only inside the worker container.

Docker Compose runs a short `config-permissions` service before the worker starts. It executes `chmod 600 config.yaml` on the host-mounted file and then exits. The worker starts only after that one-shot service completes successfully.

This protects against accidental local reads by other Unix users. It does not encrypt the secret; IMAP still requires the worker to read the real password.

## Runtime Config

Runtime settings live in environment variables. Defaults are committed in `.env.default`; local overrides go into `.env`, which is ignored by git.

Worker variables:

- `DESPAMIZER_WORKER_POLL_INTERVAL_SECONDS`: worker loop interval, default `300`.
- `DESPAMIZER_WORKER_DRY_RUN`: logs planned moves without changing mailboxes, default `true`.
- `DESPAMIZER_LOG_RETENTION_DAYS`: file log retention, default `30`.

State variables:

- `DESPAMIZER_STATE_PATH`: SQLite path inside the container, default `/app/state/despamizer.sqlite`.
- `DESPAMIZER_STATE_RETENTION_DAYS`: local state retention, default `365`.

Spam policy variables:

- `DESPAMIZER_SPAM_SCORE_MIN`: local regex score threshold, default `5.0`.
- `DESPAMIZER_RULE_TEXT_MAX_CHARS`: max sender, subject, or body characters evaluated by custom regex rules, default `200000`.
- `DESPAMIZER_SPAMASSASSIN_ENABLED`: enables SpamAssassin scoring, default `true`.
- `DESPAMIZER_SPAMASSASSIN_HOST`: internal spamd host, default `spamassassin`.
- `DESPAMIZER_SPAMASSASSIN_PORT`: internal spamd port, default `783`.
- `DESPAMIZER_SPAMASSASSIN_TIMEOUT_SECONDS`: spamd timeout, default `15`.
- `DESPAMIZER_SPAMASSASSIN_REQUIRED_SCORE`: SpamAssassin threshold override, default `5.0`.
- `DESPAMIZER_SPAMASSASSIN_MESSAGE_BYTES_MAX`: max bytes sent to SpamAssassin, default `5000000`.

Learning variables:

- `DESPAMIZER_LEARNING_ENABLED`: enables feedback learning, default `true`.
- `DESPAMIZER_LEARNING_RESCUED_HAM`: learns rescued inbox messages as ham, default `true`.
- `DESPAMIZER_LEARNING_MANUAL_SPAM`: learns manually placed spam as spam, default `true`.
- `DESPAMIZER_LEARNING_SCAN_SPAM_FOLDER`: scans spam folders for manual feedback, default `true`.
- `DESPAMIZER_LEARNING_SPAM_FOLDER_MESSAGES_MAX`: max spam-folder messages checked per mailbox per cycle, default `100`.

SpamAssassin container variables:

- `SA_UPDATE_INTERVAL_SECONDS`: rule update interval, default `86400`.
- `SPAMD_MAX_CHILDREN`: spamd worker processes, default `2`.

## Classification Order

Despamizer uses these signals:

- Whitelist wins first and prevents a move.
- Blacklist marks the message as spam.
- Regex rules add local score.
- SpamAssassin adds automatic classification.

A message is moved when local score reaches `DESPAMIZER_SPAM_SCORE_MIN` or SpamAssassin marks it as spam.

Inbox scans fetch headers first. Full message content is fetched only when needed for body rules, SpamAssassin scoring, or rescued-ham learning. Decisive sender/subject rules and allow/block lists avoid full-message fetches.

## Learning And State

Despamizer stores local state in SQLite. Docker Compose mounts host `./state` to `/app/state`, and the SQLite file is created automatically.

The database stores fingerprints, message IDs, sender, subject, status, learning class, and expiry timestamps. It does not store full message bodies.

Feedback behavior:

- If Despamizer moved a message to spam and the same message later appears in the inbox, it is treated as rescued ham, learned as ham, and skipped.
- If a message appears in the spam folder and Despamizer did not move it there, it is treated as manual spam feedback and learned as spam.
- Fingerprints are remembered so the same message is not learned repeatedly.
- When spam retention permanently deletes remote messages, matching local state rows are removed too.
- Expired state rows are cleaned according to `DESPAMIZER_STATE_RETENTION_DAYS`.

## SpamAssassin

SpamAssassin runs locally in the `spamassassin` container. It can use local rules, Bayes learning, and network checks depending on SpamAssassin configuration.

Global SpamAssassin settings live in `docker/spamassassin/local.cf`. The container runs `sa-update` on startup and then every `SA_UPDATE_INTERVAL_SECONDS`.

Oversized messages are trimmed before they are sent to SpamAssassin. Despamizer preserves the message headers and sends a bounded body sample according to `DESPAMIZER_SPAMASSASSIN_MESSAGE_BYTES_MAX`.

Bayes data and updated SpamAssassin rules are stored in the `spamassassin-state` Docker volume.

Spam retention cleanup searches the spam folder by IMAP date criteria and fetches headers only before deleting matching old messages.

## Development

Run tests and lint inside Docker:

```bash
make check
```

Refresh the lock file inside Docker:

```bash
make lock
```

GitHub Actions run lint, tests, dependency audit, secret scanning, and filesystem vulnerability scanning on pushes and pull requests.

## Safety Model

- Inbox processing only performs `inbox_folder` to `spam_folder` moves.
- Permanent deletion and IMAP expunge are used only for messages already in the configured `spam_folder` and older than mailbox `retention`.
- Dry-run mode disables message moves, learning writes, and spam retention deletion.
- Dry-run mode is enabled by default.
- Invalid regex rules fail config loading before IMAP processing.
- Log output escapes control characters from untrusted mail data to prevent log forging.
- Regex matching and SpamAssassin payloads use configurable size limits to reduce resource-exhaustion risk.
- The worker container uses a read-only root filesystem, no Linux capabilities, `no-new-privileges`, and a tmpfs `/tmp`.
- One mailbox failure is logged and does not stop other mailboxes.
- SpamAssassin is internal to Compose and is not exposed through host ports.

## License

Despamizer is licensed under the GNU Affero General Public License v3.0 or later. See `LICENSE`.

## Requirements

- Docker with Compose support.
- IMAP mailbox credentials.
