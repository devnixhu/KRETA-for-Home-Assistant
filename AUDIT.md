# Initial repository audit

This document records the state found before the KRÉTA Secure hardening work.

## Current architecture

The downloaded tree used the `kreta` domain and an aiohttp client embedded in
the integration. A config flow collected an institution code, user identifier,
password, refresh interval and look-ahead period. The client performed an
HTML-form authorization-code login, stored a refresh token in a Home Assistant
`Store`, and kept the password in the config entry and in memory. One
`DataUpdateCoordinator` fetched profile, timetable, announced tests, grades,
homework and school-year data on every update. Calendar, sensor, binary-sensor
and button platforms consumed the combined coordinator payload.

## Security findings

### Critical

None confirmed.

### High

- User-controlled institution identifiers were interpolated into hostnames
  without strict validation.
- General API requests followed redirects automatically, so a trusted KRÉTA
  endpoint could redirect an authenticated request to an untrusted host.
- The password was persisted indefinitely and used as an automatic fallback
  after refresh-token rejection.

### Medium

- Error paths logged complete HTTP response bodies and sometimes complete
  malformed records, potentially exposing personal data.
- Network operations were concentrated in one client file but had no reusable
  destination policy and several direct session calls bypassed the request
  wrapper.
- Authentication did not support a KRÉTA 2FA challenge.
- The refresh button bypassed any manual-refresh throttle.
- CI actions referenced mutable tags (`master`, `main`, and major-only tags).

### Low

- Exception messages included full URLs and raw server text.
- Authentication diagnostics contained institution identifiers and broad
  response summaries.
- The integration name and documentation did not communicate the privacy
  boundary accurately.

### Informational

- The runtime dependency list was already empty and Home Assistant's shared
  aiohttp session was used.
- API access was read-only in the inspected code.

## Privacy findings

The client requested a full student profile, including name, birth name,
birthplace, birth date, mother's name, telephone and email. These values were
normalized, retained for the coordinator lifetime, and exposed by a profile
sensor. Recorder exclusions reduced historical storage but did not prevent
runtime disclosure. Full timetable, grade, homework and school-calendar
payloads were serialized into entity attributes. Logs included the account
identifier, institution code, student name and sometimes malformed API
records or raw error bodies. Home Assistant stored the username and password
in the config entry and the refresh token in `.storage/kreta_tokens`.

## Network map

Runtime code could contact:

- `idp.e-kreta.hu`: login pages and OAuth token exchange;
- `<institution>.e-kreta.hu`: read-only `/ellenorzo/v3/Sajat/*` API data;
- any destination reached through an automatically followed redirect.

The last item made the effective map wider than the intended topology.

## Authentication analysis

The password was used for an HTML form login and then retained permanently in
the config entry. Access tokens existed in memory. Refresh tokens were stored
using Home Assistant `Store` and rotated when a new token was returned. If a
refresh token was rejected, it was deleted and the stored password was used
automatically. Reauthentication existed but also persisted the replacement
password. No logout/revocation endpoint was called, and no 2FA step existed.

## Architecture problems

- Feature groups were not independently configurable and every refresh fetched
  all endpoints.
- Coordinator data contained redundant raw JSON strings.
- Entity state was used as a data transport/database for large records.
- No persisted event baseline existed, so native new-item/change events were
  absent.
- Response schemas and collection sizes were weakly validated.
- User-visible names were mostly hard-coded instead of translation keys.
- Diagnostics, repairs, event entities, messages and absences were missing.

## Existing good parts

- The integration already used ConfigFlow, OptionsFlow,
  DataUpdateCoordinator, ConfigEntry, DeviceInfo and the Home Assistant aiohttp
  session.
- Runtime requirements were empty.
- Refresh-token rotation and reauthentication foundations existed.
- Multiple accounts used separate config entries and stable per-entry unique
  IDs.
- API operations were read-only, asynchronous and covered by a substantial
  mocked test suite.
- The upstream MIT licence and original attribution were present and must be
  retained.
