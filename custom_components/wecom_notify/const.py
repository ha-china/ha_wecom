"""Constants for the WeCom Notify integration."""

from typing import Final

DOMAIN: Final = "wecom_notify"

CONF_BOT_ID: Final = "bot_id"
CONF_SECRET: Final = "secret"
CONF_AGENT_ID: Final = "agent_id"

ATTR_MESSAGE: Final = "message"
ATTR_TARGET: Final = "target"
ATTR_TOUSER: Final = "touser"
ATTR_TEXT: Final = "text"

SERVICE_SEND_MESSAGE: Final = "send_message"
SERVICE_TEST_CONVERSATION: Final = "test_conversation"

DEFAULT_NAME: Final = "企业微信"

WS_URL: Final = "wss://openws.work.weixin.qq.com"

CMD_SUBSCRIBE: Final = "aibot_subscribe"
CMD_HEARTBEAT: Final = "ping"
CMD_SEND_MSG: Final = "aibot_send_msg"
CMD_RESPOND_MSG: Final = "aibot_respond_msg"
CMD_RESPOND_WELCOME: Final = "aibot_respond_welcome_msg"
CMD_MSG_CALLBACK: Final = "aibot_msg_callback"
CMD_EVENT_CALLBACK: Final = "aibot_event_callback"

EVENT_ENTER_CHAT: Final = "enter_chat"
