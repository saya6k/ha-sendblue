"""Constants for the Sendblue integration."""

DOMAIN = "sendblue"

CONF_API_KEY_ID = "api_key_id"
CONF_API_SECRET_KEY = "api_secret_key"
CONF_WEBHOOK_BASE_URL = "webhook_base_url"
CONF_WEBHOOK_SECRET = "webhook_secret"
CONF_CONVERSATION_AGENT_ID = "conversation_agent_id"

DEFAULT_CONVERSATION_AGENT_ID = "conversation.home_assistant"
CONF_LAST_LINE = "last_line"

SUBENTRY_RECIPIENT = "recipient"
CONF_ADDRESS = "address"
CONF_ASSIST_ENABLED = "assist_enabled"

SERVICE_SEND_MESSAGE = "send_message"
ATTR_MEDIA_URL = "media_url"
ATTR_SEND_STYLE = "send_style"
SEND_STYLES = [
    "celebration",
    "shooting_star",
    "fireworks",
    "lasers",
    "love",
    "confetti",
    "balloons",
    "spotlight",
    "echo",
    "invisible",
    "gentle",
    "loud",
    "slam",
]
