# Changelog

## 0.0.1 — initial beta
- Real-world Home Assistant entity controller with independent per-load manual overrides.
- Edit/add/remove/reorder loads via options flow.
- Solar capacity allocation excluding battery charging; EVSE current modulation.
- 16:00 boiler hard daily cutoff, 15:30 fallback and thermostat-based completion latch.
- Towel-warmer post-boiler heating and configurable 16:00–20:00 grid fallback.
- Native configuration, diagnostics, persistence and iPhone notifications.
- Configurable per-load time windows (including overnight), weekdays and scheduled auto/forced ON/forced OFF behavior.
- Optional entity-state and boiler-completion preconditions with independent manual overrides.

### GitHub / HACS distribution preparations
- Added local Home Assistant brand icon for 2026.3+.
- Added Hassfest and HACS repository validation workflows.
- Documented HACS custom-repository installation and update procedure.
- Marked integration as locally polling (20-second control tick).
