from __future__ import annotations

from ticketmaster.cli.main import build_parser


def test_cli_required_commands_parse():
    parser = build_parser()

    cases = [
        ["health"],
        ["config", "check"],
        ["db", "migrate"],
        ["db", "seed-dev"],
        ["user", "create-internal", "--email", "a@example.test", "--name", "A", "--role", "Admin"],
        ["partner", "create", "--name", "Partner"],
        ["client", "create", "--partner", "partner", "--name", "Client"],
        ["partner-user", "invite", "--partner", "partner", "--email", "u@example.test", "--name", "U", "--role", "responsible"],
        ["ticket", "create-internal", "--type", "Question", "--priority", "Normal", "--title", "T", "--description", "D"],
        ["gitlab", "check"],
        ["email", "test", "--to", "ops@example.test"],
        ["notifications", "retry-failed"],
        ["smoke", "check"],
        ["smoke", "cleanup", "--dry-run"],
    ]

    for argv in cases:
        parsed = parser.parse_args(argv)
        assert callable(parsed.func)
