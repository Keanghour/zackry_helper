# API Testing Guide (`zackry test`)

A tool for testing the **performance** and **security** of APIs you own —
FastAPI and Spring Boot. It only talks to APIs you configure yourself,
and never modifies their source code.

This guide covers **Phase 1: configuring your APIs**. Performance and
security testing, reports and exports are built in later phases — the
menu already shows where each one will live.

## Install

The testing tool needs extra packages, so it is an optional "extra":

```bash
pip install "zackry-cli[test]"
```

If you only installed `zackry-cli` without `[test]`, running `zackry test`
tells you to install it.

## Run it

```bash
zackry test
```
(or the shorter `zackry perf`)

You'll see the main menu:

```
API TESTING TOOL
 ❯ Configure APIs
   Test FastAPI
   Test Spring Boot
   Test Both APIs
   Performance Testing
   Security Testing
   Run All Tests
   View Previous Results
   Export Report
   Exit
```

Right now, only **Configure APIs** does something. The rest show when
they're coming.

## Configure APIs

**Configure APIs** lets you:
- **List APIs** — see what you've configured
- **Add API** — name, base URL, a default timeout, default authentication,
  then as many endpoints as you want (method, path, headers, a JSON body
  for POST/PUT/PATCH, and an optional auth override just for that endpoint)
- **Edit API** — change the basics, add an endpoint, or remove one
- **Delete API** — remove it, with a confirmation first

## Where things are saved

```
your-project/
├── .env                     ← your real secrets (never commit this)
└── config/
    ├── endpoints.json       ← your APIs and endpoints (no secrets)
    └── .env.example         ← the env var NAMES your config needs
```

**`config/endpoints.json`** is safe to commit to git — it never contains a
token or API key, only which APIs and endpoints to test.

**Secrets never go in the config.** When you set up authentication, you
are asked for the *name* of an environment variable (for example
`STAGING_API_TOKEN`), not the token itself. The tool writes that name into
`config/.env.example` with an empty value, so you know what to set. Put the
real value in your own `.env` file, which `zackry i` already adds to
`.gitignore`.

Example:

```
# config/.env.example  (safe to commit)
STAGING_API_TOKEN=

# .env  (never commit this)
STAGING_API_TOKEN=the-real-token-here
```

## Authentication types

- **None** — no auth header is sent
- **Bearer token** — sends `Authorization: Bearer <value>`, where
  `<value>` comes from the env var you name
- **API key** — sends a custom header (default `X-API-Key`) with a value
  from the env var you name

You can set a default for the whole API and override it per endpoint
(useful for a public health-check endpoint next to private ones).

## What's next

- **Phase 2** — the HTTP client that actually calls your configured endpoints
- **Phase 3** — performance testing (response time, P95/P99, requests/sec)
- **Phase 4** — security testing (auth checks, input validation, headers)
- **Phase 5** — console reports
- **Phase 6** — PDF / CSV / XLSX / JSON export

Each phase only ever tests APIs you have explicitly configured here, and
every heavier load test will ask for confirmation before it runs.