# System overview

The Streamlit app manages Species → Variety → Rack → Vessel records. Racks carry species-defined metadata and optional local photos; vessels record passage, medium batch, subculture date, contamination status and notes. The dashboard supplies admin-only inventory CSV, printable QR label sheets and audit exports. Shared-password admin access uses a user-supplied display label, not verified individual identity. Five failed login attempts cause a one-minute delay for that browser session, not server-wide rate limiting.

QR codes are generated locally from `BASE_URL` and cached by their full target URL. Scanners must be able to reach that URL; changing it requires new printed labels. Legacy QR service URLs are converted locally without network requests. Images are resized and saved as local JPEGs under `assets/images`; assets must be backed up separately from the database.

The database defaults to SQLite and can be configured through `DB_PATH`; an existing legacy `data/inventory.db` is reused when the newer default file does not exist. The SQLite backup download uses the active database. PostgreSQL requires an external backup tool. Missing or placeholder admin passwords disable admin access. The app is a prototype and requires deployment-specific access controls and HTTPS on untrusted networks.
