# Changelog

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog and this project uses Semantic Versioning.

## [0.2.1] - 2026-02-20

### Added
- Rules file download from list by clicking the filename in the Rules panel.
- Composer send progress bar shown while message submission is in progress.
- Chat-only scrolling layout (header and composer stay visible).
- Theme-adaptive minimal scrollbars in light and dark mode.
- Assistant response Markdown rendering with sanitization.
- Chat message meta header updated to show model/time plus `ENCODED` and `DECODED` counters.

## [0.2.0] - 2026-02-18

### Added
- Response mode selector in UI with forced output formats (`txt`, `md`, `docx`, `xlsx`, `csv`) plus `same_as_input`.
- File output generation and download endpoint for assistant responses.
- Session delete button in sidebar and related backend API.
- Theme button SVG icon and refined chat UX.
- Rules/list extensions (`BRAND`, `NAMES`) and reversed name-order matching support.
- Project-level semantic version source via `VERSION` file.
- MIT license file.
