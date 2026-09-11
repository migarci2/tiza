# Privacy and operation

Tiza is a hosted classroom service. Teachers can see attempts in their authorized classes. It does not inherit nema's local-only storage promise. The public demo contains synthetic identities and should not accept real pupils or sensitive material. A real pilot is limited to consenting adults until retention, deletion, responsibility and school-specific requirements have been defined.

Never expose Supabase service credentials, database credentials, issuer private keys or AWS credentials to Vite. There is no direct browser connection to PostgreSQL, Redis or Bedrock. Materials are private and authorized via the API. Request bodies and provider errors must not be copied wholesale into logs.

Authorization is implemented in the backend for every user query. The PostgreSQL migration enables RLS and revokes table privileges from `PUBLIC`, `anon` and `authenticated` for Tiza's 23 application tables. It installs no browser-access policies. A table owner or privileged database connection can bypass RLS; the backend's scoped authorization remains mandatory for that connection. Use a separate migration credential operationally, and explicitly configure any restricted application role before changing the database connection.

Nema permissions are narrow, expire, and can be revoked. A signed object proves control of its signing key, not a learner's academic identity. Linking requires an authenticated request and explicit consent. New fraction concept IDs still need confirmed alignment in the vault.

## Backup and restore

Use Supabase managed backups/PITR according to the plan available in your account and keep an encrypted logical backup under your organization's retention policy. Back up the private Storage objects separately and keep the issuer key in a managed secret store. Do not put backups in this repository.

For a restoration rehearsal, create an isolated database, restore the logical dump with `pg_restore --no-owner --dbname "$RESTORE_DATABASE_URL" backup.dump`, apply pending Alembic migrations, restore private objects, and run the API test flow against synthetic data. Verify organization isolation, attempts/evidence counts, approvals and pending delivery records before moving traffic. Stop the old beat/worker before starting replacements to avoid two schedulers. Do not reset uncertain deliveries to queued after a restore; reconcile them with provider records.

No educational diagnosis, retention improvement, grade impact or time saving is claimed without a separate evaluation.
