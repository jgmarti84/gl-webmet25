@AGENTS.md

## Base path (frontend)

The site can be served under a prefix (`https://host/nacho/`) that the proxy in front strips and announces with
`X-Forwarded-Prefix`; nginx writes it into each page's `<base href>`. So **app URLs never start with `/`**:

- In HTML, JS and CSS write them relative: `api/v1/...`, `css/...`, `js/...`, `assets/...`, `login`, `./` (the map).
- Every new page carries `<base href="/">` right after `<meta charset>` (nginx replaces exactly that text).
- To compare or build full browser paths use `basePath()` / `appPath()` from `frontend/public/js/shared/base-path.js`.
- `history.replaceState/pushState` with a `#` take the full path (`` `${location.pathname}${location.search}#x` ``).

Details in `docs/COMPONENTS.md` ("Base path"). `tests/e2e/test_base_path.py` browses every page behind a `/pfx/`
proxy and fails if the browser asks for anything outside it.

## User manual and design decisions

Every feature or spec, before it is closed, checks whether these files need an update, and the update goes in the
same change:

- `docs/MANUAL_DE_USUARIO.md`: when something the user sees or does changes (screens, buttons, roles, rules,
  messages).
- `docs/DESIGN_DECISIONS.md` and `docs/DESIGN_DECISIONS.es.md` (always both, same content): when a decision was made
  that the code does not explain (why it was done this way, which alternatives were turned down, which risk was
  accepted), or when an earlier decision changed. Changed decisions are not deleted: mark them "Changed" / "Cambió"
  and say what changed.

If a feature touches none of them, say so explicitly when closing it.
