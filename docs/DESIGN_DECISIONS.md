# Design decisions — accounts, access and operations

This document records **why** the accounts, permissions and access features of WebMet25 are built the way they are:
the decisions that cannot be read from the code, the alternatives that were turned down and what each choice costs.
It is meant for whoever takes over the project. What the system does and how to operate it are in
[`DATA_FLOW.md`](DATA_FLOW.md), [`COMPONENTS.md`](COMPONENTS.md) and [`OPERATIONS.md`](OPERATIONS.md); some points are
repeated here on purpose, seen from the "why" side. A Spanish version is in
[`DESIGN_DECISIONS.es.md`](DESIGN_DECISIONS.es.md).

Each entry has: **Context** (the problem), **Decision**, **Alternatives** (and why not) and **Consequences** (what is
gained, what is lost, what is left for later). Decisions that were later changed say so.

**Contents**

1. [Authentication and sessions](#1-authentication-and-sessions)
2. [Login wall](#2-login-wall)
3. [Public sign-up and mails](#3-public-sign-up-and-mails)
4. [Google sign-in](#4-google-sign-in)
5. [Roles and permissions](#5-roles-and-permissions)
6. [Institutions (company accounts)](#6-institutions-company-accounts)
7. [Invitations](#7-invitations)
8. [Deleting users and institutions](#8-deleting-users-and-institutions)
9. [Profile and mail texts](#9-profile-and-mail-texts)
10. [Storm tracking tool](#10-storm-tracking-tool)
11. [Infrastructure and performance](#11-infrastructure-and-performance)
12. [Testing](#12-testing)
13. [Interface](#13-interface)
14. [Known gaps](#14-known-gaps)

---

## 1. Authentication and sessions

### 1.1 Short JWT access token plus a rotating refresh token, both in `HttpOnly` cookies

- **Context:** the site had only nginx Basic Auth on the admin panel. Users and sessions were needed.
- **Decision:** a 30-minute signed JWT (HS256, PyJWT) as access cookie, and an opaque refresh token that rotates on
  every use, both `HttpOnly`, `Secure` and `SameSite=Strict`. A session dies after 48 h without use and 7 days at
  most. The frontend renews the access token on its own shortly before it expires.
- **Alternatives:** tokens in `localStorage` (readable by any script, so an XSS steals the session); server-side
  sessions only (simpler, but a database read on every request was already planned for other reasons, see 1.2, so
  the JWT mostly saves parsing work and keeps the tile check database-free, see 11.2).
- **Consequences:** no token is reachable from JavaScript. The first design had 15 minutes; it was raised to 30 to
  halve refresh traffic, which is the most expensive auth operation (it locks and writes a row).

### 1.2 Every authenticated request reads the user from the database

- **Context:** a JWT stays valid until it expires. Deactivating someone or resetting a password should cut access at
  once, not up to 30 minutes later.
- **Decision:** after checking the signature, each request loads the user (one primary-key read) and compares
  `is_active` and `token_version`. Raising `token_version` invalidates every access token of that user immediately.
- **Alternatives:** trusting the JWT alone (cheaper, but revocation would lag); caching the user (complexity without
  evidence of need).
- **Consequences:** one small query per request. The one exception is the basemap tiles (11.2). Permissions are
  **not** put in the JWT either (5.5).

### 1.3 One `user_sessions` row per login, with stolen-token detection

- **Context:** the first version wrote one row per refresh, so the table grew fast, and a stolen refresh token could
  be used without anyone noticing.
- **Decision:** the refresh token is `<login id>.<secret>`; each refresh rotates the secret **in the same row**.
  Presenting an old secret of that login (reuse) closes the login and raises `token_version`, which also kills the
  thief's access tokens. A 10-second window accepts the previous secret so two tabs refreshing at once get a
  "refresh race" answer instead of being logged out. Rows are locked with `SELECT ... FOR UPDATE` while rotating.
  Closed logins are purged after 90 days when that user logs in again.
- **Alternatives:** a family id plus one row per token (what existed; more rows, same detection with more work); no
  reuse detection (a stolen token keeps working for up to 7 days).
- **Consequences:** a thief and the real user cannot both keep a session: the first one to reuse an old token closes
  it. The purge needs no scheduled job. The audit log (`auth.sessions`) never contains tokens.

### 1.4 Password storage and policy

- **Decision:** Argon2id (via `pwdlib`); at least 10 characters with one special character; a password reset by mail
  cannot reuse the current password. 5 failed logins lock the account for 15 minutes. The policy applies when a
  password is created or changed, not at login, so accounts with an older, weaker password keep working.
- **Alternatives:** `passlib` and `python-jose` were avoided because they are poorly maintained.
- **Consequences:** an attacker cannot lock an account forever; a locked-out user waits or asks an admin.

### 1.5 The first admin comes from `.env`; an admin cannot reset their own password from the panel

- **Decision:** `db-init` creates the first admin from `ADMIN_USERNAME`/`ADMIN_PASSWORD` only when there are no
  users. An admin's own password is changed on the server (`make reset-password`).
- **Why:** `make up` leaves a usable system with no manual step, and taking over an admin account requires server
  access, not only a stolen session.

### 1.6 Roles as a string with a `CHECK` constraint, not a PostgreSQL `ENUM`

- **Why:** adding a role later (which happened: `org_admin`) is a constraint change, not an `ALTER TYPE`, which is
  awkward in migrations.

---

## 2. Login wall

### 2.1 The whole site requires a session; nginx guards the pages, the API guards the data

- **Context:** the map and the API were public.
- **Decision:** every data router requires a session in the API. nginx asks the API (`auth_request` to
  `/api/v1/auth/check`) before serving each HTML page, so without a session the browser never gets the page.
  Static files (`.js`, `.css`, images) stay public.
- **Alternatives:** protecting pages only in JavaScript (the page would flash and could be read); protecting static
  files too (one more database read per file, protecting nothing: they carry no data).
- **Consequences:** the real protection is the API, so bypassing nginx (for example through port 8000, which is bound
  to localhost) gains nothing.

### 2.2 The login is served "in place"

- **Decision:** a protected URL without a session answers with the login page at the same URL (status 401); after
  logging in, the page reloads.
- **Why:** nginx cannot build a `?next=` parameter that safely carries a URL with `&`. Serving in place keeps the
  original URL with no encoding.

### 2.3 The basemap tile proxies are closed too

- **Why:** an open proxy to OpenStreetMap would break its usage policy and could get the server's IP blocked.

---

## 3. Public sign-up and mails

### 3.1 Sign-up is off by default and needs its pieces in place

- **Decision:** `REGISTRATION_ENABLED=false` by default; it only turns on when mail is configured, and when
  `TERMS_REQUIRED=true` also the terms and privacy URLs. Invitations (7) work even with sign-up off.
- **Why:** opening sign-up to the public is a decision for the institution (legal texts, mail sender reputation,
  real client IP behind the proxy), not a side effect of a deploy.

### 3.2 The account is created at sign-up, inactive until the mail is verified

- **Decision:** the account exists right away (reserving the username) but cannot log in until the link in the mail is
  opened. An unverified account can be replaced by a new sign-up with its username or mail **only after its link
  expired** (24 h).
- **Alternatives:** keep pending sign-ups in a separate table (more code, and the username would not be reserved);
  let anyone replace an unverified account at any time (anyone could hijack a sign-up in progress).
- **Consequences:** no cleanup job is needed for usernames to become free again (but see 13).

### 3.3 Neutral answers, so nobody can learn which mails have an account

- **Decision:** signing up with a mail that already has an account gets the same answer as a new mail; the owner of
  that mailbox receives an "you already have an account" mail instead. The username, in contrast, answers 409
  explicitly, because people need to pick another one. The password is hashed in every case so response times do not
  leak anything, and mails are sent after the response.
- **Consequences:** a little more machinery (a mail log row with no token) to protect people's privacy.

### 3.4 Single-use tokens, stored hashed, carried after `#`

- **Decision:** 256-bit tokens, only their SHA-256 stored, one use each. The link is `/verify#token=...`; the page
  reads the fragment and posts it.
- **Why:** the fragment never reaches the server, so tokens never land in nginx logs or `Referer` headers. A static page
  that posts (instead of a link that acts on GET) prevents mail scanners from spending the token by opening the link.

### 3.5 Sending caps per account and site-wide, sent from a small thread pool

- **Decision:** per-address caps (per hour, minimum interval) and global caps per hour and per day (the daily one stops
  everything; the hourly one still lets password recovery out). Mails go out from a dedicated pool of 2 threads with a
  bounded queue.
- **Why:** a script signing up many different addresses would otherwise burn the sender's reputation and the
  provider's quota. A slow SMTP server must not hold the threads that serve the map.

### 3.6 No CAPTCHA (for now)

- **Why:** per-IP limits, per-account caps, neutral answers and mail verification were enough to start. It can be
  added later without changing the rest.

### 3.7 Mail design: logo inline, no visible token, "do not reply"

- **Decision:** the link only lives inside the button (the HTML never prints the URL); the logo travels inside the mail;
  the sender is "WebMet25 (no responder)" with no `Reply-To`, and auto-replies are suppressed.
- **Why:** mail clients block remote images; a visible token invites copy-paste mistakes; replies to a no-reply
  address would be lost.

---

## 4. Google sign-in

- **Decision:** the browser shows Google's button; the API checks the signed ID token against Google's public keys.
  The account is found by Google's fixed id (`sub`) first, then by mail. Google must have verified the mail. With no
  account, a viewer is created with the mail already verified. **General admins can never sign in with Google.**
  Linking an account that was never verified drops its password and closes its sessions.
- **Alternatives:** finding accounts by mail only (a person who changes their Google mail would lose access);
  allowing admins (a compromised Google account would become a full admin).
- **Consequences:** whoever set a password on an unverified account does not own the mailbox; the Google user does,
  so that password is discarded. When an admin changes an account's mail, its Google link is dropped (the `sub`
  belonged to the old mail), and the person links again on their next Google login.

---

## 5. Roles and permissions

### 5.1 Three roles, and permissions as separate grants

- **Context:** the institution wanted to decide, person by person, which radars' detail view each one can open, and
  later to hand out other features.
- **Decision:** the role says **what kind of user** someone is (`admin`, `org_admin`, `viewer`); what they can open
  lives in a `permissions` table: **who** (a user or an institution) + **action** + **resource**.
- **Alternatives:** one role per combination ("viewer with RMA1 and RMA17"), which explodes; a classic role/permission
  table, which cannot express "this institution admin narrows this one person's list".
- **Consequences:** a new feature is a new action string, not new tables (see the tool registry in 10). The resource is
  text, so there is no foreign key to the radar: the admin endpoint deletes the permissions of a radar in the same
  transaction as the radar.

### 5.2 A permission opens the detail view, not the data

- **Decision:** the permission decides who can open `radar.html`. Data endpoints are the same for everyone with a
  session, and everyone keeps seeing every radar on the main map.
- **Why:** the detail view uses the same endpoints as the map. Hiding data per user would have touched every router
  and the shared frame cache, for data people already see on the map.

### 5.3 The radar's `detail_view_enabled` flag means "the view is ready"

- **Decision:** opening a view needs the flag **and** the permission; the general admin only needs the flag.
- **Why:** "the view is configured" and "who may see it" are different things. Turning the flag off (maintenance)
  hides the view for everyone without touching anybody's list.

### 5.4 "All" is a wildcard that includes future radars

- **Decision:** `*` as resource.
- **Why:** whoever gets "all" expects to see new radars too; assigning radar by radar would be forgotten.

### 5.5 Permissions are read from the database, not carried in the JWT

- **Context:** putting them in the token was considered to save queries.
- **Decision:** they are read when a page asks for `/permissions/me` (once per page load), not on every request.
- **Why:** they are only needed when opening the view, so the saving is small; tools and future per-feature lists
  would make the cookie large; and a change would need the token to expire (or a `token_version` bump) to show.

### 5.6 New accounts start with no views

- **Decision:** self sign-up, Google sign-up and existing accounts at the time of the migration all started with no
  views; an admin assigns them.
- **Why:** a permission is always an explicit grant. The cost: after that deploy only the admin could open detail
  views until views were assigned.

---

## 6. Institutions (company accounts)

### 6.1 Institutions with a seat limit and their own permissions

- **Decision:** an institution (for example a utility company) has a **seat limit** (active users, admins included),
  its own views and tools, and one or more **institution admins** who manage its members from a limited panel
  (`/empresa`). On screen it is called "institución"; in the code and the database it keeps `organization` /
  `org_admin`.
- **Why a separate panel:** `/admin` is protected by nginx for the general admin role; hiding sections with JavaScript
  would protect nothing.

### 6.2 What a member sees = their own list ∩ the institution's list, computed when read

- **Decision:** a member's effective views (and tools) are the intersection of their own grants and the institution's.
  An institution admin sees the institution's list.
- **Why:** if the institution loses a radar, every member loses it at once, without touching their rows. A new member
  starts with a **copy** of the institution's list, and the institution admin can narrow it per person, never widen it.

### 6.3 Seats

- **Decision:** deactivating frees a seat; reactivating takes one; lowering the limit below the active users
  deactivates nobody (it only blocks new ones). Seats are checked with the institution row locked.
- **Why:** without the reactivation rule the limit could be bypassed by deactivating and reactivating; without the
  lock, two simultaneous sign-ups could both take the last seat.

### 6.4 An institution with active users always has an active admin

- **Decision:** the API refuses (409) to demote, deactivate, unlink or delete the only active admin while other active
  users remain, and refuses to add a viewer to an institution with no active admin.
- **Why:** members of an institution without an admin would have nobody to manage them. An institution with no users
  may have no admin.

### 6.5 Institution admins unlink people; only the general admin moves accounts

- **Decision:** the institution admin "unlinks" a viewer (the account stays, as a viewer with no institution and no
  views) instead of deactivating them. Moving an account between institutions, or adding an existing account, is done
  by the general admin. Entering an institution replaces the account's views and tools with a copy of the
  institution's; leaving removes them; both close the account's sessions.
- **Why:** an institution admin should not be able to lock someone out of the whole site, nor pull accounts away from
  another institution.
- **Changed:** at first an account's institution was fixed when it was created; later the general admin was allowed
  to move accounts.

### 6.6 Creating an institution is all or nothing

- **Decision:** name, seats, its admin (new, existing viewer, invitation, or none) and its views and tools are created
  in one request inside one transaction.
- **Why:** a half-created institution (for example created but with a failed admin) was confusing to fix by hand.

---

## 7. Invitations

- **Decision:** an admin can invite a person by mail instead of creating the account with a password. The general
  admin invites institution admins or viewers to any institution; an institution admin invites viewers to its own,
  within its own views and tools. The link (`/invitacion#token=...`) lasts 7 days and is single use. A **pending
  invitation reserves a seat**. A Google sign-in must use the invited mail.
- **Inviting someone who already has an account:** allowed. The invitation page asks the server whether the mail has an
  account **when the link is opened** (nothing is stored) and shows a login instead of the sign-up form. Joining needs
  **both** the link and a session of that mail's account, so the link alone cannot enter anybody's account. Only the
  general admin can invite a viewer of another institution (accepting moves them).
- **Why not just tell the inviter "that mail has an account":** the inviter is already an admin, so that is not a leak,
  but asking them to go through the general admin every time was too much friction for a common case.
- **Consequences:** invitation rows are never deleted (accepted, cancelled and expired stay as a record) and they count
  for the mail sending caps.

---

## 8. Deleting users and institutions

### 8.1 Deleting users is real, after a period of "deactivate only"

- **Changed decision:** at first users were never deleted, only deactivated, to keep identity for a future audit. It
  was changed to a real delete: the general admin deletes others, and each person can delete their own account.
- **Rules:** a general admin cannot delete their own account (another general admin does), and the last active
  general admin cannot be deleted; the institution rule (6.4) applies. Confirmation is a manual dialog, with no
  password.
- **Accepted risk:** someone with an open session on a shared computer could delete that account. It only affects the
  own account, and general admins cannot delete themselves. Asking for the password can be added without changing the
  rest.
- **Consequences:** "who granted this" or "who invited" fields in other rows become empty; the Google link goes with the
  account, so the mail can be invited again.

### 8.2 Deleting an institution forces a choice about its users

- **Decision:** an institution with users (active or not) is not deleted until the general admin chooses to
  **unlink** them (default) or **delete** them too; deleting them requires typing the institution's name. Everything
  runs in one transaction. Pending invitations, and the history of accepted and cancelled ones, go with it.
- **Why:** deleting people's accounts as a side effect of deleting a company must be a deliberate act.

---

## 9. Profile and mail texts

### 9.1 One profile page; only the name is editable

- **Decision:** `/perfil` for every role (inside the panel for admins). Username and mail are read only there.
- **Why:** changing the mail means verifying it again, and changing the username breaks how people know each other;
  both stay with the admins. A profile photo was designed but left out (no uploads, no volume).

### 9.2 Mail texts editable from the panel, design fixed in the code

- **Decision:** the general admin can edit the text of the four mails (subject, title, paragraphs, button text,
  footer). The logo, layout, the button and its link, and the "do not reply" notice stay in the code. A row exists
  only when a mail was customized; otherwise the text in the code is used. Placeholders (`{usuario}`, ...) are
  validated when saving.
- **Why:** wording changes should not need a deploy, but the link with the token and the layout must not be breakable
  from the panel. With no row, a deploy never changes a mail by surprise. Text is plain (any HTML is shown as text).

---

## 10. Storm tracking tool

### 10.1 A yes/no tool, not a list of radars

- **Decision:** storm tracking is a **tool** (`tool.tracking`, resource `*`) that a user or an institution has or not.
  It appears in every radar view the person can open.
- **Alternatives:** a per-radar tracking permission (a second list duplicating the views).
- **Consequences:** taking a radar's view away also takes its tracking; no extra list to keep in sync.
- **Changed:** the panel's "Vistas" section became "Herramientas" and holds the views and this tool.

### 10.2 Same rules as the views, plus "turning it on reaches everyone"

- **Decision:** member = own grant ∩ institution's; the institution admin can only give it if the institution has it;
  invitations carry the choice. When the general admin turns the tool on for an institution, **every current member
  gets it**; the institution admin removes it from whoever should not have it.
- **Why:** turning a tool on for an institution and then having to tick every member by hand was the common complaint.
  The panel warns when a grant has no effect (for example a member of an institution without the tool).

### 10.3 Enforced by nginx, and per radar on the per-radar routes

- **Decision:** the tracking service has no notion of sessions; nginx is its only gate. Every `/api/tracking/` route
  and the `/tracking` page need the tool; the routes that carry the radar in the URL
  (`/api/tracking/radars/<code>/...`) need the tool **and** that radar's view.
- **Why:** a tracking job costs seconds of CPU, so hiding the button is not enough. The radar was put in the URL of the
  newer routes precisely so nginx can check it without reading the body.
- **Consequences:** the older routes (`POST /api/tracking/jobs`, `/api/tracking/availability`), used only by the test
  page `tracking.html`, only check the tool. Usage limits (per user or per IP) were left for later; the service runs
  one job at a time and shares identical requests.

### 10.4 Adding a tool is a checklist

- **Decision:** tools are listed in one registry (`TOOLS` in the API, `TOOL_LIST` in the frontend); a test fails and
  says which step was forgotten. See [`OPERATIONS.md`](OPERATIONS.md), "How to add a tool".

---

## 11. Infrastructure and performance

### 11.1 Database pool sized so every worker fits in PostgreSQL

- **Context:** each Uvicorn worker has its own pool; 4 workers × (10 + 20) = 120 possible connections against
  PostgreSQL's 100. Under a burst, the extra connections were refused and requests failed.
- **Decision:** `DB_MAX_OVERFLOW=12` for the API (4 × 22 = 88), passed from compose so each server can tune it with
  the number of workers.
- **Alternatives:** raising `max_connections` (more memory, and more concurrent queries are not faster on the same
  cores); PgBouncer (right answer at a larger scale, not needed yet).
- **Consequences:** extra requests wait a few milliseconds in the pool instead of failing. Raising `UVICORN_WORKERS`
  requires redoing the arithmetic.

### 11.2 Basemap tiles check the JWT alone, without reading the database

- **Context:** panning the map asks for dozens of basemap tiles at once, and each one went through the full session
  check (1.2), using a database connection per tile.
- **Decision:** the tile proxies ask a lighter probe (`/api/v1/auth/check-token`) that only verifies the signed access
  token, `async` and with no database session.
- **Consequences:** an exception to 1.2: a deactivated user keeps receiving basemap tiles (public OSM/IGN images) until
  the access token expires (30 minutes at most). Everything else is cut at once.

### 11.3 Real client IP behind the proxies

- **Context:** on stage the chain is Tailscale Funnel → Caddy → nginx. nginx saw Docker's gateway as the client of
  every request, so the per-IP limits were one counter for the whole internet.
- **Decision:** nginx trusts `X-Forwarded-For` only from Docker networks and localhost (`set_real_ip_from`,
  `real_ip_recursive on`) and reads it from the right; Caddy trusts the local proxy (`trusted_proxies`). nginx is
  published on `127.0.0.1` by default (`FRONTEND_BIND`).
- **Why from the right:** whatever a client writes in that header ends up on the left, so it cannot fake its address.

### 11.4 Base path: the same image can be served under a prefix

- **Context:** two copies of the site had to share one hostname (`/` and `/nacho/`).
- **Decision:** the proxy strips the prefix and announces it in `X-Forwarded-Prefix`; nginx validates it (one simple
  segment) and writes it into each page's `<base href>`; app URLs are always relative; cookie names and the refresh
  path carry the prefix.
- **Alternatives:** a fixed `BASE_PATH` variable (the same copy would not work both with and without the prefix);
  rewriting every nginx location (invasive).
- **Consequences:** a team rule: **app URLs never start with `/`** (see [`COMPONENTS.md`](COMPONENTS.md), "Base
  path"). `tests/e2e/test_base_path.py` browses every page behind a test proxy and fails if anything escapes the
  prefix. `history.replaceState` with a `#` must use the full path, or it resolves against `<base>`.

---

## 12. Testing

### 12.1 Black-box tests run against an isolated stack

- **Context:** the API and e2e suites create users and sessions; they ran against the development database.
- **Decision:** `tests/api` and `tests/e2e` run against their own API, frontend and database (`api-e2e`,
  `frontend-e2e`, `radar_e2e_db`), on a private Docker network, using another Redis index.
- **Consequences:** the suites never write to the real data. Happy paths that write are tested in process in
  `tests/auth`, against the test database; `tests/api` only checks error paths of writing endpoints.

### 12.2 Concurrency rules have their own tests

- **Decision:** the locks (refresh rotation, last seat of an institution) are tested with two real connections and a
  forced pause, because a normal test would pass even without the lock.

---

## 13. Interface

### 13.1 One tooltip of our own, a floating bubble

- **Context:** the browser draws a `title` as a box with a dark border that cannot be styled, and a tooltip written in CSS
  inside a table was hidden by the sticky header (and clipped by the table's scrolling box).
- **Decision:** one bubble, a child of `<body>` with `position: fixed`, fed by every `title` of the page (also the ones
  the code sets later) and by the `<title>` inside icons. It opens above its control and flips below when there is no
  room.
- **Alternatives:** a `::after` on each control (clipped by `overflow` and by stacking contexts; it failed in the
  tables); keeping the browser's own (no control over look or timing).
- **Consequences:** the text moves from `title` to `data-tooltip` and `aria-label`; text fields are skipped because their
  `title` is also part of the browser's format message. A page with tooltips loads one script.

### 13.2 Our own confirmation window instead of `window.confirm`

- **Decision:** `confirmAction` is a small window with the motion of the others, answering a promise. For an action that
  cannot be undone the red button does it and the focus starts on Cancel.
- **Why:** the browser box cannot be styled or animated and looks different on every system. The cost is that every
  question became asynchronous, and the e2e tests answer the window (`answer_confirmation`) instead of the browser
  dialog.

### 13.3 One account chip for the map and the panels, in two themes

- **Decision:** the same pill (avatar, name, role, logout) everywhere; every color is a variable. The map keeps the dark
  theme; the panels use a light one, because a dark pill stood out too much in a light header. In the light theme the
  general admin's badge is blue (the color of the panel) and the institution admin's is slate.
- **Alternatives:** a different chip in each place (they drifted apart); the dark pill in the panels (too loud); a
  yellow badge for the general admin (it did not fit the blue panels).
- **Consequences:** the shortcut to the panel of the role exists only on the map; a panel has only logout, since the
  person is already there.

### 13.4 Row actions as icons; the rare ones live under "Seguridad"

- **Context:** the users table had too many buttons per row.
- **Decision:** icons with a tooltip for the frequent ones (edit, tools, delete); **Seguridad** (a padlock) opens a
  window with reset password, close sessions and deactivate or activate. Delete is its own trash button, at the end
  and white (a red fill drew too much attention).
- **Alternatives:** smaller text buttons (it only delays the problem), moving the rare ones into the edit form.

### 13.5 Collapsible side menu; the active group always open

- **Decision:** the groups open and close with a soft animation. The group that holds the active link is always open. In
  the admin panel the others start closed, because its menu is long; the institution and profile panels have a couple
  of links, so everything starts open. What the person opens is remembered, for each panel on its own.
- **Turned down:** an animated radar sweep as the background of the sidebar. It was tried (rings and a beam, CSS only)
  and removed: it was only visible at the bottom and did not convince. The login panel keeps its radar and takes the
  color of the sidebar.

### 13.6 "Mis datos" as one compact card

- **Decision:** the head (avatar, name, `@user`, role, "Editar nombre") and, under a line, the data that is not already
  in the head. Two big cards repeated the username, the name and the role.

### 13.7 Motion: short, soft and easy to turn off

- **Decision:** windows, notices, sections, table rows and search lists animate briefly, with transform and opacity only
  (the browser does it on the graphics card). Closing a window fades out first and only then empties its form. A section
  animates when it changes, not when the same one is drawn again after an action (it would blink).
- **Why:** it helps the eye follow what changed; it must never delay what the person wants to do, so everything stops
  with `prefers-reduced-motion`.
- **Left for later:** the floating panels of the map open with an animation but still close at once.

---

## 14. Known gaps

These were left out on purpose and are worth knowing:

- No cleanup job for unverified accounts and expired mail tokens; nginx logs have no rotation.
- Accounts created by an admin never see the terms checkbox.
- No CAPTCHA, and no usage limits for the tracking service.
- Accepting an invitation whose radar was deleted in the meantime fails (the invitation keeps the code).
- The legal texts (terms and privacy) are not written yet; sign-up cannot require them until they exist.
