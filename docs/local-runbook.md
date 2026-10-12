# Local runbook — database roles and analytics RLS

## Safety boundary

Migration `0002_analytics_security` changes privileges and RLS metadata only. It does not insert, update, delete, truncate, or re-import source rows. Run it first on a separately restored test database whose name contains `test`; never use a runtime or reader credential for Alembic. The rehearsal database **must run in a separate PostgreSQL cluster/instance**, not merely another database in the production/local cluster: PostgreSQL roles are cluster-wide and the three fixed reader group names intentionally fail closed when already present.

Prerequisites for the migration account:

- the P1-T02 backup gate has been completed;
- it can alter the four source tables `public.properties`, `public.transactions`, `public.offers`, and `public.repairs`;
- it can create the three fixed `NOLOGIN` group roles below;
- no role named `analytics_reader_all`, `analytics_reader_ca`, or `analytics_reader_tx` already exists;
- the four source tables have no pre-existing RLS configuration. The migration fails closed instead of replacing one.
- no source table/column grants to `PUBLIC`, no `PUBLIC CREATE` on `public`, `analytics`, or `app`, and no unreviewed non-owner consumers of the four scoped tables. Privileges are additive and enabling RLS would default-deny existing consumers, so the migration aborts instead of silently weakening or breaking their access.

## Apply on the restored test database

```powershell
$env:MIGRATION_DATABASE_URL = '<migration-role-url-on-restored-test-db>'
$env:MIGRATION_BACKUP_VERIFIED = 'true'
Push-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

The migration creates these passwordless group roles:

- `analytics_reader_all`
- `analytics_reader_ca`
- `analytics_reader_tx`

It never creates a login or stores a password. An operator creates three distinct login roles using the normal PostgreSQL secret-management workflow, grants each login exactly one group role, and ensures every login is `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`. Do not grant reader groups to one another. Do not grant readers database/schema `CREATE`, source ownership, or membership in an owner role.

Example membership commands, with environment-specific login identifiers substituted as SQL identifiers:

```sql
GRANT analytics_reader_all TO <all_login_role>;
GRANT analytics_reader_ca  TO <ca_login_role>;
GRANT analytics_reader_tx  TO <tx_login_role>;
```

Set passwords interactively or through the approved secret store; never add them to migration SQL, the repository, command history, or logs.

## Configure the backend

```powershell
$env:READER_ALL_DATABASE_URL = '<url-for-all-login>'
$env:READER_CA_DATABASE_URL = '<url-for-ca-login>'
$env:READER_TX_DATABASE_URL = '<url-for-tx-login>'
```

The backend requires an explicit `ALL`, `CA`, or `TX` scope and selects only the corresponding pool. Missing or unknown scope fails; there is no fallback to `ALL`. Reader usernames must be distinct from each other and from configured runtime/migration usernames. On the first connection in each pool, the backend verifies the actual PostgreSQL principal: exact expected group membership, no other inherited role, no superuser/BYPASSRLS/DDL/ownership path, and `INHERIT` enabled. A swapped DSN or over-privileged login fails before serving a query.

## Integration verification

Only point these variables at the separately restored test database:

```powershell
$env:READER_ALL_TEST_DATABASE_URL = '<all-reader-url-on-test-db>'
$env:READER_CA_TEST_DATABASE_URL = '<ca-reader-url-on-test-db>'
$env:READER_TX_TEST_DATABASE_URL = '<tx-reader-url-on-test-db>'
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_rls.py -q
```

The test verifies direct tables and `security_invoker` views, CA/TX totals, offers/repairs isolation, PII denial, mutation/DDL denial, role attributes, ownership, and inability to switch into another scope. A skipped test is a blocker, not a pass.

Before downgrade, stop reader traffic. The downgrade removes the views, policies, grants, RLS enablement, and the three group roles; it does not modify source rows. Dropping a group also removes login memberships. The migration-cycle integration test re-provisions memberships from `READER_*_TEST_DATABASE_URL` after its final upgrade; an operator performing a manual cycle must do the same.

## Auth and demo users

Set `FRONTEND_ORIGIN` to the exact browser origin (default local value: `http://localhost:3000`). The backend rejects login/logout unless exactly one `Origin` header matches; validation errors never echo submitted values. Configure `RUNTIME_DATABASE_URL` with the non-owner application role, then supply all four `SEED_*_PASSWORD` values shown in `backend/.env.example` and run `backend/scripts/seed_users.py`. Passwords shorter than 12 characters are rejected and no default password exists. Re-seeding resets the four identities and revokes their active sessions in the same locked transaction.

For authentication integration tests, set `AUTH_TEST_DATABASE_URL` only to a database whose name contains `test`. The suite creates isolated random users, checks fixation/expiry/revocation and removes them afterward. Missing credentials cause a documented skip and remain a release blocker.
