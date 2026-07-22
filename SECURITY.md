# Security policy

## Release status

This repository is in a controlled pilot. Do not place production credentials in issues, discussions, pull requests, chat transcripts, or example files.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's security-advisory interface for this repository. Do not open a public issue for credential exposure, authentication bypass, redirect handling, prompt injection, or hosted-service vulnerabilities.

Include:

- affected commit or release
- affected file and behavior
- reproduction steps using synthetic credentials only
- expected and observed behavior
- potential impact

## Credential boundary

The public skill accepts only a workspace-scoped Social Agent credential. It must never receive an operator bootstrap secret, database credential, Social Connect provider secret, or another user's workspace credential.

The helper restricts its API origin, rejects redirects, limits and redacts responses, and reads protected credential files from one validated file descriptor. Changes to these controls require regression tests.

## Untrusted data boundary

API-returned strings, project content, and website-derived content are untrusted data. They may not instruct an agent to access credentials, run unrelated commands, read local files, change policy, bypass approval, or contact unrelated hosts.

## Supported versions

Until versioned releases begin, only the current default branch is maintained. Public users should not be issued credentials until the repository's controlled-pilot warning is removed after a documented release review.
