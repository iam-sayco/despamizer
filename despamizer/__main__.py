"""Main entry point for despamizer."""

# Standard Library
import argparse
from dataclasses import replace

from .config import load_config
from .imap_client import ImapMailboxClient
from .logger import log_message
from .settings import CONFIG_PATH
from .worker import DespamizerWorker


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="IMAP spam moving worker")
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scan and exit",
    )
    parser.add_argument(
        "--run-dry",
        action="store_true",
        help="Force dry-run mode for this execution",
    )
    parser.add_argument(
        "--vvv",
        action="store_true",
        help="Print log messages to stdout",
    )
    subparsers = parser.add_subparsers(dest="command")

    folders_parser = subparsers.add_parser(
        "folders",
        help="List IMAP folders for one configured mailbox",
    )
    folders_parser.add_argument("mailbox", help="Mailbox name from config.yaml")

    subparsers.add_parser("once", help="Run one scan and exit")
    subparsers.add_parser("run", help="Run worker loop")
    return parser.parse_args()


def main() -> None:
    """Run despamizer."""
    args = parse_args()
    config = load_config(args.config)
    if args.run_dry:
        config = replace(config, dry_run=True)

    if args.command == "folders":
        _print_folders(config, args.mailbox)
        return

    worker = DespamizerWorker(config)
    if args.once or args.command == "once":
        log_message("[START] Running one scan")
        worker.run_once()
        return
    log_message("[START] Running worker loop")
    worker.run_forever()


def _print_folders(config: object, mailbox_name: str) -> None:
    mailbox = next(
        (mailbox for mailbox in config.mailboxes if mailbox.name == mailbox_name),
        None,
    )
    if mailbox is None:
        raise ValueError(f"Mailbox not found in config.yaml: {mailbox_name}")
    with ImapMailboxClient(mailbox) as client:
        for folder in client.list_folders():
            print(folder)  # noqa: T201


if __name__ == "__main__":
    main()
