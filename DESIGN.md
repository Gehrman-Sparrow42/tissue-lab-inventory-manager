---
name: Lab Inventory
description: A practical workspace for locating and maintaining tissue culture inventory.
colors:
  ink: "#19283d"
  muted: "#526277"
  primary: "#1d4ed8"
  primary-hover: "#163eae"
  navy: "#173457"
  canvas: "#f5f7fb"
  line: "#dce3ed"
  surface: "#fff"
  secondary-surface: "#edf1f7"
  input-line: "#c6d1df"
  clean-text: "#17613c"
  clean-surface: "#e7f4ed"
  critical-text: "#992d38"
  critical-surface: "#fbecef"
  warning-text: "#7e5109"
  warning-surface: "#fff2d8"
typography:
  headline:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
    fontSize: "2rem"
    fontWeight: 650
    lineHeight: 1.22
    letterSpacing: "-.025em"
  title:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
    fontSize: "1.3rem"
    fontWeight: 650
    letterSpacing: "-.015em"
  body:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
    lineHeight: 1.55
  label:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
    fontSize: ".85rem"
    fontWeight: 550
rounded:
  badge: "5px"
  navigation: "7px"
  control: "8px"
  container: "12px"
spacing:
  form: "1.25rem"
  table-horizontal: "1.1rem"
  table-vertical: ".75rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    height: "40px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    height: "40px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  work-container:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.container}"
    padding: "{spacing.form}"
---

## Overview

**Creative North Star**

A clear inventory workspace.

Staff can scan record names and locations, navigate the collection, and reach editing actions in a familiar workspace. The interface uses a navy navigation rail, a cool canvas, white work surfaces, blue actions and compact labels. Native controls and readable record details support desktop use and phone scans.

**Key Characteristics**

- Navigation remains distinct from the main work area.
- Inventory names and parent locations lead the reading order.
- A restrained palette carries action, hierarchy and culture status.

## Colors

Blue identifies primary actions and record links. Navy anchors the navigation rail. The canvas, white surfaces and pale dividers separate work areas. Green, red and amber badges distinguish clean, contaminated and suspected culture states. Neutral badges cover other values. Text accompanies every status color.

## Typography

Segoe UI with system sans-serif fallbacks is used throughout. Page headings are the strongest type, followed by section headings. Body text stays relaxed and labels and table headings are compact. On small screens the page heading becomes 1.7rem and section headings become 1.18rem.

## Layout

The desktop rail is 240px wide. Main content is capped at 1380px and uses 2.6rem top and 3rem horizontal padding. At 900px the horizontal padding becomes 1.5rem, and at 600px it becomes 1rem. The detail grid changes from two columns to one at 600px. Inventory table rows become compact two-column records on narrow screens, keeping location and status visible. The sidebar uses Streamlit's automatic responsive behavior.

## Elevation & Depth

The custom stylesheet relies on surface color and thin borders for separation. It defines no reusable shadow tokens.

## Shapes

Controls have gently rounded corners. Forms, expanders and inventory containers use a larger radius, and status badges use a tighter radius. Borders are light and quiet.

## Components

### Buttons and fields

Primary actions use blue with white text. Secondary actions use a white surface and outline. Buttons have a minimum height of 40px and change background and border on hover. Text and selection fields use white surfaces with a subtle border. A visible blue focus outline supports keyboard navigation.

### Navigation rail

The rail groups the brand and page links. Links have a 44px minimum height, a lighter hover surface and a distinct active surface. The geometric mark is inline SVG. Long link labels wrap rather than truncate.

### Inventory records

The record table presents record, location, type and culture status. Names link to records and identifiers appear beneath. On narrow screens the table retains its semantic headers while each row is visually rearranged into two columns. Location text wraps, and the status remains adjacent to the record.

### Location trails and status badges

Location trails show the inventory hierarchy as a wrapping list separated by slashes. Badges pair short status text with a color-coded surface. The clean, contaminated and suspected values have distinct tones, while other values use a neutral tone.

### Forms and empty states

Forms and expanders sit on bordered white surfaces. Empty states use a dashed border, a short heading and muted explanatory text.

## Do's and Don'ts

### Do

- Do keep record names, parent locations and culture status easy to scan.
- Do use native controls and preserve visible keyboard focus.
- Do retain readable labels and wrapping locations on narrow screens.

### Don't

- Don't rely on color alone to convey culture status.
- Don't truncate navigation labels or long locations when they can wrap.
- Don't add decorative raster assets to the inventory workspace without a product need.
