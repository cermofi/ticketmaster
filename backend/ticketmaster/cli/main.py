from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.core.database import SessionLocal, engine
from ticketmaster.models import Client, GitLabLink, Partner, Ticket, User
from ticketmaster.models.entities import new_id
from ticketmaster.schemas.serializers import client_to_dict, partner_to_dict, ticket_to_dict, user_to_dict
from ticketmaster.services import admin, gitlab, migrations, notifications, search, seed, smoke_check, smoke_cleanup, tickets
from ticketmaster.services.errors import TicketMasterError
from ticketmaster.services.internal_roles import set_internal_roles
from ticketmaster.services.rate_limit import list_rate_limit_keys, reset_rate_limits


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str, ensure_ascii=False))


def cli_actor(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == "cli-system@ticketmaster.local"))
    if user:
        return user
    user = User(
        id=new_id(),
        email="cli-system@ticketmaster.local",
        name="TicketMaster CLI",
        kind="internal",
        active=True,
    )
    set_internal_roles(user, ["Admin"])
    db.add(user)
    db.flush()
    return user


def cmd_health(_: argparse.Namespace) -> int:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print_json({"status": "ok", "database": "ok"})
    return 0


def cmd_config_check(_: argparse.Namespace) -> int:
    print_json(
        {
            "database_url": _redact(settings.database_url),
            "base_url": settings.base_url,
            "smtp": {
                "host": settings.smtp_host,
                "port": settings.smtp_port,
                "from": settings.smtp_from,
                "tls": settings.smtp_tls,
                "suppress_send": settings.mail_suppress_send,
            },
            "gitlab": gitlab.check_configuration(),
            "upload_dir": settings.upload_dir,
        }
    )
    return 0


def cmd_db_migrate(_: argparse.Namespace) -> int:
    applied = migrations.run_migrations(engine)
    print_json({"applied": applied, "status": "ok"})
    return 0


def cmd_db_seed_dev(_: argparse.Namespace) -> int:
    if not settings.allow_seed_dev:
        print("error: db seed-dev is disabled in this environment (set ALLOW_SEED_DEV=true for local dev)", file=sys.stderr)
        return 1
    migrations.run_migrations(engine)
    with session_scope() as db:
        print_json(seed.seed_dev(db))
    return 0


def cmd_user_create_internal(args: argparse.Namespace) -> int:
    with session_scope() as db:
        user = admin.create_internal_user(
            db,
            email=args.email,
            name=args.name,
            role=args.role,
            roles=args.roles,
            actor=cli_actor(db),
            source="cli",
        )
        print_json(user_to_dict(user))
    return 0


def cmd_user_deactivate(args: argparse.Namespace) -> int:
    with session_scope() as db:
        user = admin.deactivate_user(db, email=args.email, actor=cli_actor(db), source="cli")
        print_json(user_to_dict(user))
    return 0


def cmd_user_list(_: argparse.Namespace) -> int:
    with session_scope() as db:
        print_json([user_to_dict(user) for user in db.scalars(select(User).order_by(User.email)).all()])
    return 0


def cmd_partner_create(args: argparse.Namespace) -> int:
    with session_scope() as db:
        partner = admin.create_partner(db, name=args.name, actor=cli_actor(db), source="cli")
        print_json(partner_to_dict(partner))
    return 0


def cmd_partner_list(_: argparse.Namespace) -> int:
    with session_scope() as db:
        print_json([partner_to_dict(partner) for partner in db.scalars(select(Partner).order_by(Partner.name)).all()])
    return 0


def cmd_client_create(args: argparse.Namespace) -> int:
    with session_scope() as db:
        client = admin.create_client(db, partner_key_or_id=args.partner, name=args.name, actor=cli_actor(db), source="cli")
        print_json(client_to_dict(client))
    return 0


def cmd_client_list(args: argparse.Namespace) -> int:
    with session_scope() as db:
        partner = admin.resolve_partner(db, args.partner)
        print_json([client_to_dict(client) for client in db.scalars(select(Client).where(Client.partner_id == partner.id).order_by(Client.name)).all()])
    return 0


def cmd_partner_user_invite(args: argparse.Namespace) -> int:
    with session_scope() as db:
        user = admin.invite_partner_user(
            db,
            partner_key_or_id=args.partner,
            email=args.email,
            name=args.name,
            role=args.role,
            actor=cli_actor(db),
            source="cli",
        )
        data = user_to_dict(user)
        data["invitation_token"] = user.invitation_token
        data["dev_password"] = settings.dev_password
        print_json(data)
    return 0


def cmd_partner_user_deactivate(args: argparse.Namespace) -> int:
    return cmd_user_deactivate(args)


def cmd_client_assign_responsible(args: argparse.Namespace) -> int:
    with session_scope() as db:
        assignment = admin.assign_responsible_to_client(
            db,
            client_key_or_id=args.client,
            user_email_or_id=args.user,
            actor=cli_actor(db),
            source="cli",
        )
        print_json({"id": assignment.id, "client_id": assignment.client_id, "user_id": assignment.user_id})
    return 0


def cmd_ticket_show(args: argparse.Namespace) -> int:
    with session_scope() as db:
        ticket = tickets.get_ticket(db, args.id)
        print_json(ticket_to_dict(db, ticket, include_detail=True))
    return 0


def cmd_ticket_transfer_owner(args: argparse.Namespace) -> int:
    with session_scope() as db:
        ticket = tickets.get_ticket(db, args.id)
        tickets.transfer_owner(db, ticket=ticket, actor=cli_actor(db), new_owner_ref=args.new_owner, source="cli")
        print_json(ticket_to_dict(db, ticket, include_detail=True))
    return 0


def cmd_ticket_assign(args: argparse.Namespace) -> int:
    with session_scope() as db:
        ticket = tickets.get_ticket(db, args.id)
        tickets.assign_ticket(db, ticket=ticket, actor=cli_actor(db), team=args.team, assignee_ref=args.assignee, source="cli")
        print_json(ticket_to_dict(db, ticket, include_detail=True))
    return 0


def cmd_ticket_close(args: argparse.Namespace) -> int:
    with session_scope() as db:
        ticket = tickets.get_ticket(db, args.id)
        tickets.close_ticket(db, ticket=ticket, actor=cli_actor(db), source="cli")
        print_json(ticket_to_dict(db, ticket, include_detail=True))
    return 0


def cmd_ticket_create_internal(args: argparse.Namespace) -> int:
    with session_scope() as db:
        actor = cli_actor(db)
        ticket = tickets.create_internal_ticket(
            db,
            actor=actor,
            ticket_type=args.type,
            priority=args.priority,
            title=args.title,
            description=args.description,
            team=args.team,
            source="cli",
        )
        print_json(ticket_to_dict(db, ticket, include_detail=True))
    return 0


def cmd_gitlab_check(_: argparse.Namespace) -> int:
    print_json(gitlab.check_configuration())
    return 0


def cmd_gitlab_create_issue(args: argparse.Namespace) -> int:
    with session_scope() as db:
        ticket = tickets.get_ticket(db, args.ticket)
        link = gitlab.create_main_issue(db, ticket=ticket, actor=cli_actor(db), source="cli")
        print_json({"ticket_id": ticket.id, "web_url": link.web_url, "status": link.status})
    return 0


def cmd_gitlab_sync_status(args: argparse.Namespace) -> int:
    with session_scope() as db:
        ticket = tickets.get_ticket(db, args.ticket)
        link = gitlab.sync_status(db, ticket=ticket, actor=cli_actor(db), source="cli")
        print_json({"ticket_id": ticket.id, "web_url": link.web_url, "status": link.status})
    return 0


def cmd_email_test(args: argparse.Namespace) -> int:
    with session_scope() as db:
        row = notifications.queue_email(db, event="email_test", recipient_email=args.to, subject="TicketMaster CLI test e-mail", body="TicketMaster CLI SMTP test.", ticket_id=None)
        notifications.retry_failed(db)
        print_json({"id": row.id, "status": row.status, "last_error": row.last_error})
    return 0


def cmd_notifications_retry_failed(_: argparse.Namespace) -> int:
    with session_scope() as db:
        print_json({"sent": notifications.retry_failed(db)})
    return 0


def cmd_search_reindex_tickets(_: argparse.Namespace) -> int:
    with session_scope() as db:
        print_json({"indexed": search.reindex_tickets(db)})
    return 0


def cmd_smoke_check(args: argparse.Namespace) -> int:
    result = smoke_check.run_smoke_check(base_url=args.base_url, email=args.email, password=args.password)
    print_json(result)
    return 0 if result["status"] == "ok" else 1


def cmd_rate_limit_reset(args: argparse.Namespace) -> int:
    if not args.ip and not args.identifier and not args.scope:
        print("error: provide at least one of --ip, --identifier, or --scope", file=sys.stderr)
        return 1
    removed = reset_rate_limits(ip=args.ip, identifier=args.identifier, scope=args.scope)
    print_json({"removed": removed, "status": "ok"})
    return 0


def cmd_rate_limit_list(_: argparse.Namespace) -> int:
    print_json({"keys": list_rate_limit_keys()})
    return 0


def cmd_smoke_cleanup(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.confirm:
        print("error: pass --confirm to delete smoke artifacts (or use --dry-run to preview)", file=sys.stderr)
        return 1
    with session_scope() as db:
        result = smoke_cleanup.cleanup_smoke_artifacts(
            db,
            marker_only=not args.include_seed_artifacts,
            dry_run=args.dry_run,
        )
        result["discovery_sql"] = smoke_cleanup.sql_discovery_queries(marker_only=not args.include_seed_artifacts)
        print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ticketmaster-cli")
    sub = parser.add_subparsers(dest="command", required=True)

    _command(sub, "health", cmd_health)

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="subcommand", required=True)
    _command(config_sub, "check", cmd_config_check)

    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="subcommand", required=True)
    _command(db_sub, "migrate", cmd_db_migrate)
    _command(db_sub, "seed-dev", cmd_db_seed_dev)

    user = sub.add_parser("user")
    user_sub = user.add_subparsers(dest="subcommand", required=True)
    p = _command(user_sub, "create-internal", cmd_user_create_internal)
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", choices=["Admin", "DeliveryManager", "L1", "L2", "L3"])
    p.add_argument("--roles", nargs="+", choices=["Admin", "DeliveryManager", "L1", "L2", "L3"])
    p = _command(user_sub, "deactivate", cmd_user_deactivate)
    p.add_argument("--email", required=True)
    _command(user_sub, "list", cmd_user_list)

    partner = sub.add_parser("partner")
    partner_sub = partner.add_subparsers(dest="subcommand", required=True)
    p = _command(partner_sub, "create", cmd_partner_create)
    p.add_argument("--name", required=True)
    _command(partner_sub, "list", cmd_partner_list)

    client = sub.add_parser("client")
    client_sub = client.add_subparsers(dest="subcommand", required=True)
    p = _command(client_sub, "create", cmd_client_create)
    p.add_argument("--partner", required=True)
    p.add_argument("--name", required=True)
    p = _command(client_sub, "list", cmd_client_list)
    p.add_argument("--partner", required=True)
    p = _command(client_sub, "assign-responsible", cmd_client_assign_responsible)
    p.add_argument("--client", required=True)
    p.add_argument("--user", required=True)

    partner_user = sub.add_parser("partner-user")
    partner_user_sub = partner_user.add_subparsers(dest="subcommand", required=True)
    p = _command(partner_user_sub, "invite", cmd_partner_user_invite)
    p.add_argument("--partner", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", required=True, choices=["responsible", "technical"])
    p = _command(partner_user_sub, "deactivate", cmd_partner_user_deactivate)
    p.add_argument("--email", required=True)

    ticket = sub.add_parser("ticket")
    ticket_sub = ticket.add_subparsers(dest="subcommand", required=True)
    p = _command(ticket_sub, "show", cmd_ticket_show)
    p.add_argument("--id", required=True)
    p = _command(ticket_sub, "transfer-owner", cmd_ticket_transfer_owner)
    p.add_argument("--id", required=True)
    p.add_argument("--new-owner", required=True)
    p = _command(ticket_sub, "assign", cmd_ticket_assign)
    p.add_argument("--id", required=True)
    p.add_argument("--team", required=True, choices=["L1", "L2", "L3"])
    p.add_argument("--assignee")
    p = _command(ticket_sub, "close", cmd_ticket_close)
    p.add_argument("--id", required=True)
    p = _command(ticket_sub, "create-internal", cmd_ticket_create_internal)
    p.add_argument("--type", required=True)
    p.add_argument("--priority", required=True, choices=["Low", "Normal", "High", "Critical"])
    p.add_argument("--title", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--team", choices=["L1", "L2", "L3"])

    gitlab_parser = sub.add_parser("gitlab")
    gitlab_sub = gitlab_parser.add_subparsers(dest="subcommand", required=True)
    _command(gitlab_sub, "check", cmd_gitlab_check)
    p = _command(gitlab_sub, "create-issue", cmd_gitlab_create_issue)
    p.add_argument("--ticket", required=True)
    p = _command(gitlab_sub, "sync-status", cmd_gitlab_sync_status)
    p.add_argument("--ticket", required=True)

    email = sub.add_parser("email")
    email_sub = email.add_subparsers(dest="subcommand", required=True)
    p = _command(email_sub, "test", cmd_email_test)
    p.add_argument("--to", required=True)

    notif = sub.add_parser("notifications")
    notif_sub = notif.add_subparsers(dest="subcommand", required=True)
    _command(notif_sub, "retry-failed", cmd_notifications_retry_failed)

    search_parser = sub.add_parser("search")
    search_sub = search_parser.add_subparsers(dest="subcommand", required=True)
    _command(search_sub, "reindex-tickets", cmd_search_reindex_tickets)

    smoke = sub.add_parser("smoke")
    smoke_sub = smoke.add_subparsers(dest="subcommand", required=True)
    p = _command(smoke_sub, "check", cmd_smoke_check)
    p.add_argument("--base-url")
    p.add_argument("--email")
    p.add_argument("--password")
    p = _command(smoke_sub, "cleanup", cmd_smoke_cleanup)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--confirm", action="store_true")
    p.add_argument(
        "--include-seed-artifacts",
        action="store_true",
        help="Also remove known seed-dev demo entities (acme partner/client, @example.test users)",
    )

    rate_limit = sub.add_parser("rate-limit")
    rate_limit_sub = rate_limit.add_subparsers(dest="subcommand", required=True)
    p = _command(rate_limit_sub, "reset", cmd_rate_limit_reset)
    p.add_argument("--ip", help="Client IP part of the rate-limit key")
    p.add_argument("--identifier", help="E-mail (login) or user id (auth flows)")
    p.add_argument("--scope", choices=["login", "sign-in-as-partner", "back-to-admin"])
    _command(rate_limit_sub, "list", cmd_rate_limit_list)
    return parser


def _command(subparsers, name: str, func):
    parser = subparsers.add_parser(name)
    parser.set_defaults(func=func)
    return parser


def _redact(value: str) -> str:
    return value.replace(settings.gitlab_token or "___never___", "***")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except TicketMasterError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
