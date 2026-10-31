# ViaggiaTreno for Home Assistant

HACS-compatible station monitors using **ViaggiaTreno's structured API**. Includes an optional custom dashboard card in the style of the RFI station monitor.

## Installation

### HACS custom repository

Once this repository is published on GitHub:

1. Add its GitHub URL in **HACS → Custom repositories**, category **Integration**.
2. Download **ViaggiaTreno** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → ViaggiaTreno**.
4. Search a station, choose a polling interval, then select the matching station.

### Manual installation

Copy `custom_components/viaggiatreno` into the Home Assistant configuration's
`custom_components` directory, restart Home Assistant, then add the integration
through **Settings → Devices & services**.