"""Constants for ViaggiaTreno."""

from homeassistant.const import Platform

DOMAIN = "viaggiatreno"
PLATFORMS = [Platform.SENSOR]
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_REFRESH_INTERVAL = "refresh_interval"
DEFAULT_REFRESH_INTERVAL = 60
MIN_REFRESH_INTERVAL = 30
MAX_REFRESH_INTERVAL = 3600
STATIC_URL = "/viaggiatreno/static"
# The public website's API currently works over HTTP, not HTTPS.
BASE_URL = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"
