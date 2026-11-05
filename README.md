# Laboratory Inventory Manager

A Streamlit inventory for species, varieties, racks and individual vessels. Species define rack metadata fields. Rack photos and QR labels are stored locally, and QR images are generated without an external service.

## Setup

1. Install Python 3.10 or newer and dependencies with `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`. Set a private `ADMIN_PASSWORD`. Admin editing is disabled when the password is absent or a default placeholder.
3. Set `DB_PATH` if needed. The default is `data/inventory_v2.db`. An existing legacy `data/inventory.db` is reused when the newer file does not exist. Relative paths resolve from the project folder, including bare filenames.
4. Set `BASE_URL` to the HTTP(S) address reachable by the device scanning labels, such as the server's LAN address. The default `http://localhost:8501` works for scans on the server itself. Regenerate and reprint labels after changing the address.
5. Run `python -m streamlit run main.py` and visit the displayed address.

In the C:\Tools workspace, use the shared Python environment and `C:\Tools\LAUNCHERS\Launch_Tissue_Lab_Inventory_Manager.bat`. This launcher binds to loopback. To use phones on a trusted LAN, start Streamlit with an appropriate listening address and set `BASE_URL` to the reachable server address.

## Workspace navigation

Overview provides inventory search, record-type filters and sorting across the full hierarchy. It initially shows six matching records. Use **Show all matches** for the complete result set. Record links open details in a new tab, keeping the current workspace session available.

Use the sidebar for species and varieties, racks and assets, or vessels. The vessel **Filters** control groups location and culture-status filters. On phones, record summaries wrap location and status into readable rows. Admin editing forms, downloads and audit history are available after signing in.

## Inventory workflows

Guests can browse records and follow QR links. Admins can create and edit species, varieties, racks and vessels. Vessels record their parent rack, passage number, medium batch, optional subculture date, contamination status and notes. Parents containing child records cannot be deleted.

Schema edits and parent changes retain existing metadata, including removed or renamed fields. New fields receive defaults. Existing values incompatible with a new numeric field remain visible and must be explicitly corrected before saving the rack. Admins can repair malformed legacy JSON in the rack page. The original raw payload is retained in the audit log when the corrected JSON is saved. Legacy duplicate variety names are retained. New collisions are blocked, and existing duplicates can be renamed without deleting records.

Each UI mutation and its audit event commit together. Delete events retain readable identifiers. Audit actor labels are entered during shared-password login and are self-reported. Five failed login attempts delay that browser session for one minute. Separate verified user accounts and server-wide login throttling are outside the current authentication model.

## Exports and backups

The dashboard offers admin-only inventory CSV, printable bulk QR-label HTML, and audit CSV. The inventory export includes all hierarchy levels and raw rack metadata. Formula-like CSV cells are escaped for spreadsheet use. Open the label HTML in a browser and print it. It contains embedded QR images and works offline.

Use **Prepare Database Backup**, then **Export Database**, to download a consistent SQLite snapshot of the active database. Prepare a new snapshot to include subsequent changes. Back up `assets/images` separately to preserve uploaded photos. QR images under `assets/qrcodes` can be regenerated. PostgreSQL databases require a PostgreSQL backup tool.

New asset paths are project-relative, and legacy image paths can resolve by their managed image suffix after moving the project together with its assets. Images are validated, oriented from EXIF data, resized to at most 1600 × 1600 pixels and saved as JPEG. Previously discarded uploads cannot be recovered from placeholder paths.

## Sample data

Run `python populate.py path/to/new-example.db` to create illustrative records in a new SQLite file. Its parent directory must exist. The command refuses an existing file and records sample creation in the audit log.

## Verification

Install development dependencies with `python -m pip install -r requirements-dev.txt`. From the repository root, create the local `.agents` directory if needed, then run `python -m pytest tests --basetemp=.agents/pytest-work`. Tests use isolated temporary databases.

The regression suite covers metadata preservation, schema validation, legacy migrations, backups, login boundaries, taxonomy forms, rack moves, vessel lifecycle, managed images, offline QR generation and exports. Live PostgreSQL connectivity and physical phone/printer behavior require checks in the target environment.

## Source layout

- `main.py` provides QR scan routing, exports and audit viewing.
- `pages/1_Species_&_Varieties.py` manages taxonomy and metadata schemas.
- `pages/2_Racks_&_Assets.py` manages racks, photos and metadata.
- `pages/3_Vessels.py` manages individual vessels.
- `modules/database.py` owns configuration, compatible migrations, audit staging and SQLite snapshots.
- `modules/validation.py` validates schemas and preserves metadata during reconciliation.
- `modules/qr_utils.py`, `modules/image_utils.py` and `modules/exports.py` supply local assets and downloads.

## Vercel hosting

The container deployment uses PostgreSQL for inventory and private Vercel Blob storage for photos. See [deployment/README.md](deployment/README.md) for runtime settings, provisioning and live verification. Local SQLite and asset files are excluded from the deployment package.
