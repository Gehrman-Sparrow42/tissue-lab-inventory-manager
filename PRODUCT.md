# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Lab staff managing species, varieties, racks and individual vessels. The user confirmed a balanced workspace that supports quick inventory browsing, clear editing and phone QR scans.

## Product Purpose

Locate biological inventory, maintain its hierarchy and metadata, and open the correct record from a physical QR label.

## Operating Context

A Streamlit web application used on desktop browsers and phone browsers. Local SQLite is the default persistence option, with PostgreSQL configuration supported. QR generation and stored photos work locally.

## Capabilities and Constraints

Species define rack metadata schemas. Varieties belong to species, racks belong to varieties and vessels belong to racks. Guests browse records. Shared-password admins edit records, repair malformed metadata, download inventory and audit CSV files, print QR sheets and prepare SQLite backups. Operator labels are self-reported. Existing metadata and audit records must remain accessible through every UI change.

## Product Principles

- Keep location and parentage visible when browsing records.
- Put common inventory tasks within easy reach.
- Make editing, validation and feedback explicit.
- Make QR record views readable on phones.

## Evidence on Hand

The existing application, database models, regression tests and prior browser-verification captures supply factual product evidence. Demonstration records used for visual verification are illustrative and remain separate from the active inventory.

## Brand Commitments

The user selected a conventional dashboard and delegated craft-reference selection. Benchling inventory, Airtable interfaces and Linear navigation guided the implementation. DESIGN.md records the resulting visual system.

## Open Decisions

No product-specific accessibility standard or brand identity has been specified. App screens use a code-first workflow for this session. No standing workflow preference for future showcase or landing-page work has been recorded.
