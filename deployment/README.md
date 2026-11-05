# Vercel deployment

This app uses Vercel's Container Runtime. The container starts the Streamlit server on the platform's PORT and uses PostgreSQL and private Supabase Storage for durable inventory and photos.

## Required runtime settings

- DATABASE_URL contains the Supabase transaction pooler PostgreSQL URL. Use the dedicated login that owns the inventory tables and can create tables in their schema. DB_PATH can explicitly override it. Hosted connections require TLS by default and use the provider's pooler.
- SUPABASE_URL is the project HTTPS URL. SUPABASE_SECRET_KEY grants server-only access to the private storage bucket; legacy SUPABASE_SERVICE_ROLE_KEY is also supported.
- SUPABASE_STORAGE_BUCKET optionally selects the private bucket (default `lab-inventory-photos`).
- ADMIN_PASSWORD enables the shared admin login. Choose a private value.
- STREAMLIT_SERVER_COOKIE_SECRET supplies the same cookie-signing secret across instances.
- BASE_URL is the production HTTPS address used in printed QR labels. The entrypoint can derive it from VERCEL_PROJECT_PRODUCTION_URL when available.

The hosted entrypoint refuses to start with a local SQLite database or missing storage and authentication settings. Credentials belong in Vercel environment variables. The repository and container upload omit local environment files, databases, photos and verification artifacts.

## Provision and deploy

1. Link the repository to the intended Vercel project and select the Container framework preset.
2. Connect the Supabase PostgreSQL database and create a private Supabase Storage bucket named `lab-inventory-photos` (or set SUPABASE_STORAGE_BUCKET to its name). Set the project URL and server-only secret key in Vercel.
3. Add the private admin password and cookie secret as sensitive production environment variables. Set BASE_URL to the production domain.
4. Run `vercel deploy --prod --scope <team>` from the repository root.
5. Verify the health endpoint, guest browsing, admin login, create/edit/delete, photo uploads and display, downloads, QR routes, concurrent browser sessions and reconnects before declaring the deployment ready.

The app enables row-level security and removes direct `anon` and `authenticated` access on its inventory tables. The Streamlit server owns the tables and mediates all access. No Supabase browser-facing policies are needed for this app.

`vercel deploy --dry --json` inspects the framework and upload manifest without publishing. Local Docker validation requires a Docker engine. Vercel builds the container remotely from Dockerfile.vercel.

## Storage behavior

Saved records live in PostgreSQL. New photos are JPEG objects in the private Supabase bucket and use managed supabase://lab-inventory/images/... references in the database. Containers download photos to temporary caches. QR images are regenerated in temporary storage. Hosted image display and downloads use inline data to avoid dependence on an individual instance's media cache.

Vercel can replace or scale down container instances. WebSocket connections follow the plan's function duration limit, so browser sessions may reconnect. A live check of Streamlit file uploads and session reconnection is required because those operations depend on the deployment's routing behavior.

The SQLite database and local photos used by the offline app are separate from the hosted database. Existing inventory requires an explicit migration. Development fixtures are excluded from deployment.
