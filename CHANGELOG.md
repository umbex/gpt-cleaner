# Changelog

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog and this project uses Semantic Versioning.

## [0.2.3] - 2026-02-20

### Added
- Chat metadata now shows explicit encoded/decoded values in the message header when present.
- Prompt guardrail for tokenized placeholders (`<TKN_...>`) to keep tokens intact in LLM output.

### Changed
- User messages are displayed as original text (not tokenized placeholders) in chat history.
- Persistent logging default set to `false` (`app` config, compose default, `.env.example`).
- Response mode default in UI set to `Same as input`.
- Minor test fixture/data refresh under `test-files/` and `rules/lists/`.

## [0.2.2] - 2026-02-20

### Added
- Assistant/user message header now shows `ENCODED` and `DECODED` counters in full.
- Assistant messages now render sanitized Markdown (e.g. `**bold**` shown as formatted text).

### Changed
- New assistant messages auto-scroll to the start of the message instead of the end.
- Improved soft-wrapping for long technical/plain-text payloads (including RTF-like content) in chat bubbles.

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
