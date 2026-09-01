# Security Policy

## Supported version

Security fixes target the latest `0.1.x` development line. This is a local single-user V0.1, not a hardened internet-facing multi-user service.

## Reporting a vulnerability

Do not post private data, exploit payloads, or credentials in a public issue. Use the repository host's private security-reporting feature when available. If the repository has no private reporting channel, open a minimal issue requesting a private contact path without including exploit details.

## Deployment boundary

`community-intelligence serve` binds to `127.0.0.1` and does not offer a public-host flag. Do not expose the service through a reverse proxy, tunnel, shared network, or public cloud without adding authentication, authorization, request isolation, retention controls, CSRF/origin review, operational logging, and a separate threat model.

Imported Telegram data is sensitive. Keep the local analysis directory private, protect workstation backups, and delete analysis workspaces according to your own retention policy. The importer hashes user/community identifiers, but source message text is retained because evidence inspection requires it.
