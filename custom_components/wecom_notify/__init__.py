"""WeCom Notify integration."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import uuid
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_MESSAGE,
    ATTR_TARGET,
    ATTR_TEXT,
    ATTR_TOUSER,
    CMD_EVENT_CALLBACK,
    CMD_HEARTBEAT,
    CMD_RESPOND_WELCOME,
    EVENT_ENTER_CHAT,
    CMD_MSG_CALLBACK,
    CMD_RESPOND_MSG,
    CMD_SEND_MSG,
    CMD_SUBSCRIBE,
    CONF_AGENT_ID,
    CONF_BOT_ID,
    CONF_SECRET,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
    SERVICE_TEST_CONVERSATION,
    WS_URL,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.NOTIFY]

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TARGET): cv.string,
        vol.Optional(ATTR_TOUSER): cv.string,
    }
)


class WeComWsClient:
    """Pure Python WeCom websocket client."""

    def __init__(self, hass: HomeAssistant, bot_id: str, secret: str) -> None:
        self.hass = hass
        self.bot_id = bot_id
        self.secret = secret

        self._session = async_get_clientsession(hass)
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._runner_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False
        self._authenticated = asyncio.Event()
        self._send_lock = asyncio.Lock()

        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._message_callback: Any = None

    def set_message_callback(self, callback: Any) -> None:
        self._message_callback = callback

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._runner_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        self._authenticated.clear()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        if self._runner_task:
            self._runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_task
            self._runner_task = None

        await self._close_ws()
        self._fail_all_pending("client stopped")

    async def send_markdown(
        self, target: str, message: str, timeout: float = 20.0
    ) -> dict[str, Any]:
        await self._ensure_authenticated(timeout=timeout)
        req_id = self._req_id(CMD_SEND_MSG)
        payload = {
            "cmd": CMD_SEND_MSG,
            "headers": {"req_id": req_id},
            "body": {
                "chatid": target,
                "msgtype": "markdown",
                "markdown": {"content": message},
            },
        }

        future: asyncio.Future[dict[str, Any]] = self.hass.loop.create_future()
        self._pending[req_id] = future
        try:
            await self._send_json(payload)
            ack = await asyncio.wait_for(future, timeout=timeout)
            if ack.get("errcode", 0) != 0:
                raise RuntimeError(ack.get("errmsg", "unknown error"))
            return ack
        finally:
            self._pending.pop(req_id, None)

    async def reply_markdown(
        self, callback_req_id: str, message: str, timeout: float = 20.0
    ) -> dict[str, Any]:
        await self._ensure_authenticated(timeout=timeout)
        payload = {
            "cmd": CMD_RESPOND_MSG,
            "headers": {"req_id": callback_req_id},
            "body": {
                "msgtype": "markdown",
                "markdown": {"content": message},
            },
        }

        future: asyncio.Future[dict[str, Any]] = self.hass.loop.create_future()
        self._pending[callback_req_id] = future
        try:
            await self._send_json(payload)
            try:
                ack = await asyncio.wait_for(future, timeout=timeout)
            except TimeoutError:
                _LOGGER.warning("Reply ack timeout for req_id=%s", callback_req_id)
                return {"errcode": 0, "errmsg": "ack timeout"}
            if ack.get("errcode", 0) != 0:
                raise RuntimeError(ack.get("errmsg", "unknown error"))
            return ack
        finally:
            self._pending.pop(callback_req_id, None)

    async def reply_welcome(
        self, callback_req_id: str, message: str, timeout: float = 20.0
    ) -> dict[str, Any]:
        await self._ensure_authenticated(timeout=timeout)
        payload = {
            "cmd": CMD_RESPOND_WELCOME,
            "headers": {"req_id": callback_req_id},
            "body": {
                "msgtype": "markdown",
                "markdown": {"content": message},
            },
        }

        future: asyncio.Future[dict[str, Any]] = self.hass.loop.create_future()
        self._pending[callback_req_id] = future
        try:
            await self._send_json(payload)
            try:
                ack = await asyncio.wait_for(future, timeout=timeout)
            except TimeoutError:
                _LOGGER.warning("Welcome ack timeout for req_id=%s", callback_req_id)
                return {"errcode": 0, "errmsg": "ack timeout"}
            if ack.get("errcode", 0) != 0:
                raise RuntimeError(ack.get("errmsg", "unknown error"))
            return ack
        finally:
            self._pending.pop(callback_req_id, None)

    async def reply_via_response_url(
        self, response_url: str, message: str, timeout: float = 15.0
    ) -> dict[str, Any]:
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": message},
        }

        async with self._session.post(response_url, json=payload, timeout=timeout) as resp:
            data = await resp.json(content_type=None)

        if not isinstance(data, dict):
            raise RuntimeError(f"invalid response_url response: {data}")
        if data.get("errcode", 0) != 0:
            raise RuntimeError(data.get("errmsg", "response_url error"))
        return data

    async def _run_loop(self) -> None:
        retry_delay = 1
        while self._running:
            try:
                _LOGGER.info("Connecting WeCom websocket: %s", WS_URL)
                ws = await self._session.ws_connect(WS_URL, heartbeat=60)
                self._ws = ws
                self._authenticated.clear()

                await self._send_auth()
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                retry_delay = 1
                await self._receive_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("WeCom websocket loop error: %s", err)
            finally:
                self._authenticated.clear()
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._heartbeat_task
                    self._heartbeat_task = None
                await self._close_ws()
                self._fail_all_pending("websocket disconnected")

            if self._running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    async def _receive_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                    break
                continue

            try:
                frame = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            await self._handle_frame(frame)

    async def _handle_frame(self, frame: dict[str, Any]) -> None:
        cmd = frame.get("cmd")
        req_id = frame.get("headers", {}).get("req_id", "")

        if cmd in (CMD_MSG_CALLBACK, CMD_EVENT_CALLBACK):
            _LOGGER.info(
                "WeCom callback received cmd=%s req_id=%s",
                cmd,
                req_id,
            )

        if cmd in (CMD_MSG_CALLBACK, CMD_EVENT_CALLBACK):
            if self._message_callback:
                await self._message_callback(frame)
            return

        pending = self._pending.get(req_id)
        if pending and not pending.done():
            pending.set_result(frame)
            return

        if req_id.startswith(CMD_SUBSCRIBE):
            if frame.get("errcode", -1) == 0:
                self._authenticated.set()
                _LOGGER.info("WeCom websocket authenticated: %s", frame)
            else:
                _LOGGER.error("WeCom auth failed: %s", frame)
            return

        if req_id.startswith(CMD_HEARTBEAT):
            return

        _LOGGER.debug("Unhandled WeCom frame: %s", frame)

    async def _heartbeat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(30)
            if not self._authenticated.is_set():
                continue
            frame = {
                "cmd": CMD_HEARTBEAT,
                "headers": {"req_id": self._req_id(CMD_HEARTBEAT)},
            }
            try:
                await self._send_json(frame)
            except Exception:  # noqa: BLE001
                return

    async def _send_auth(self) -> None:
        frame = {
            "cmd": CMD_SUBSCRIBE,
            "headers": {"req_id": self._req_id(CMD_SUBSCRIBE)},
            "body": {"bot_id": self.bot_id, "secret": self.secret},
        }
        await self._send_json(frame)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            if self._ws is None or self._ws.closed:
                raise RuntimeError("websocket not connected")
            await self._ws.send_json(payload)

    async def _ensure_authenticated(self, timeout: float) -> None:
        if self._authenticated.is_set():
            return
        await asyncio.wait_for(self._authenticated.wait(), timeout=timeout)

    async def _close_ws(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    def _fail_all_pending(self, reason: str) -> None:
        for key, future in list(self._pending.items()):
            if not future.done():
                future.set_exception(RuntimeError(reason))
            self._pending.pop(key, None)

    @staticmethod
    def _req_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _extract_text(body: dict[str, Any]) -> str:
    if body.get("msgtype") == "text":
        return body.get("text", {}).get("content", "").strip()
    return str(body.get("content", "")).strip()


def _extract_reply_target(body: dict[str, Any]) -> str:
    sender = body.get("from", {})
    return (
        sender.get("userid")
        or body.get("from_userid")
        or body.get("userid")
        or body.get("chatid")
        or "@all"
    )


def _extract_speech(response: dict[str, Any] | None) -> str:
    if not response:
        return ""
    speech = response.get("response", {}).get("speech", {}).get("plain", {})
    if isinstance(speech, dict):
        value = speech.get("speech")
        return value.strip() if isinstance(value, str) else ""
    if isinstance(speech, str):
        return speech.strip()
    return ""


def _extract_speech_any(response: Any) -> str:
    if isinstance(response, dict):
        return _extract_speech(response)

    text = ""
    try:
        plain = response.response.speech.get("plain", {})
        if isinstance(plain, dict):
            text = plain.get("speech", "")
        elif isinstance(plain, str):
            text = plain
    except Exception:  # noqa: BLE001
        pass

    if isinstance(text, str) and text.strip():
        return text.strip()

    if hasattr(response, "as_dict"):
        try:
            data = response.as_dict()
            if isinstance(data, dict):
                return _extract_speech(data)
        except Exception:  # noqa: BLE001
            pass

    return ""


def _extract_agent_id_from_obj(candidate: Any) -> str | None:
    """Extract conversation agent id from pipeline-like object."""
    if isinstance(candidate, dict):
        for key in (
            "conversation_engine",
            "conversation_agent",
            "conversation_agent_id",
            "agent_id",
        ):
            value = candidate.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    for attr in (
        "conversation_engine",
        "conversation_agent",
        "conversation_agent_id",
        "agent_id",
    ):
        value = getattr(candidate, attr, None)
        if isinstance(value, str) and value:
            return value

    return None


async def _get_preferred_agent_id(hass: HomeAssistant) -> str | None:
    """Get preferred conversation agent from Assist pipeline if available."""
    try:
        from homeassistant.components import assist_pipeline

        getter = getattr(assist_pipeline, "async_get_preferred_pipeline", None)
        if getter is not None:
            preferred = await getter(hass)
            agent_id = _extract_agent_id_from_obj(preferred)
            if agent_id:
                return agent_id
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Failed to resolve preferred assist pipeline: %r", err)

    return None


def _is_fallback_reply(reply: str) -> bool:
    normalized = reply.strip().lower()
    return normalized in {
        "sorry, i couldn't understand that",
        "sorry, i could not understand that",
        "i couldn't understand that",
        "i could not understand that",
        "抱歉，我不明白你的意思",
        "抱歉，我听不懂",
    }


async def _ask_home_assistant(
    hass: HomeAssistant, text: str, sender: str, agent_id: str | None
) -> str:
    conversation_id = f"wecom:{sender}"

    try:
        from homeassistant.components import conversation as conversation_component

        if hasattr(conversation_component, "async_converse"):
            signature = inspect.signature(conversation_component.async_converse)
            kwargs: dict[str, Any] = {}
            if "hass" in signature.parameters:
                kwargs["hass"] = hass
            if "text" in signature.parameters:
                kwargs["text"] = text
            if "conversation_id" in signature.parameters:
                kwargs["conversation_id"] = conversation_id
            if "context" in signature.parameters:
                kwargs["context"] = Context()
            if "language" in signature.parameters:
                kwargs["language"] = hass.config.language
            if "agent_id" in signature.parameters and agent_id:
                kwargs["agent_id"] = agent_id

            result = await conversation_component.async_converse(**kwargs)
            reply = _extract_speech_any(result)
            if reply:
                return reply
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("conversation.async_converse failed: %r", err)

    if hass.services.has_service("conversation", "process"):
        data: dict[str, Any] = {
            "text": text,
            "conversation_id": conversation_id,
            "language": hass.config.language,
        }
        if agent_id:
            data["agent_id"] = agent_id
        try:
            result = await hass.services.async_call(
                "conversation",
                "process",
                data,
                blocking=True,
                return_response=True,
            )
            reply = _extract_speech(result)
            if reply:
                if not _is_fallback_reply(reply):
                    return reply
                _LOGGER.info("conversation.process returned fallback reply, trying next")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("conversation.process failed: %r", err)

    if hass.services.has_service("conversation", "ask"):
        data = {"text": text, "language": hass.config.language}
        if agent_id:
            data["agent_id"] = agent_id
        try:
            result = await hass.services.async_call(
                "conversation",
                "ask",
                data,
                blocking=True,
                return_response=True,
            )
            reply = _extract_speech(result)
            if reply:
                if not _is_fallback_reply(reply):
                    return reply
                _LOGGER.info("conversation.ask returned fallback reply, using final fallback")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("conversation.ask failed: %r", err)

    return f"收到你的消息：{text}"


async def _handle_send_message(hass: HomeAssistant, call: ServiceCall) -> None:
    message = call.data.get(ATTR_MESSAGE, "")
    target = call.data.get(ATTR_TOUSER) or call.data.get(ATTR_TARGET) or "@all"
    if not message:
        return

    entries: dict[str, dict[str, Any]] = hass.data.get(DOMAIN, {})
    if not entries:
        _LOGGER.error("No configured entries for %s", DOMAIN)
        return

    runtime = next(iter(entries.values()))
    client: WeComWsClient = runtime["client"]

    try:
        await client.send_markdown(target, message)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed sending WeCom message: %s", err)


async def _handle_inbound(
    hass: HomeAssistant, runtime: dict[str, Any], frame: dict[str, Any]
) -> None:
    cmd = frame.get("cmd")
    if cmd not in (CMD_MSG_CALLBACK, CMD_EVENT_CALLBACK):
        return

    callback_req_id = frame.get("headers", {}).get("req_id", "")
    body = frame.get("body", {})
    response_url = body.get("response_url", "")

    if cmd == CMD_EVENT_CALLBACK:
        event_type = body.get("event", {}).get("eventtype") or body.get("eventtype")
        event_user = (
            body.get("event", {}).get("userid")
            or body.get("event", {}).get("chatid")
            or body.get("userid")
            or body.get("chatid")
        )
        _LOGGER.info(
            "WeCom event callback: eventtype=%s user=%s body=%s",
            event_type,
            event_user,
            body,
        )
        if event_type == EVENT_ENTER_CHAT and callback_req_id:
            if event_user:
                runtime["paired_targets"].add(event_user)
            _LOGGER.info("Enter-chat event received, sending welcome reply")
            try:
                await runtime["client"].reply_welcome(
                    callback_req_id,
                    "已连接 Home Assistant，你可以直接发送问题或控制指令。",
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Failed handling enter_chat event: %r | frame=%s", err, frame)
        return

    text = _extract_text(body)
    if not text:
        return

    target = _extract_reply_target(body)
    _LOGGER.info("Inbound message from %s: %s", target, text)
    try:
        reply = await _ask_home_assistant(hass, text, target, runtime.get("agent_id"))
        if reply:
            if response_url:
                try:
                    await runtime["client"].reply_via_response_url(response_url, reply)
                    _LOGGER.info("Replied by response_url")
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Reply by response_url failed, fallback to callback/send: %r", err
                    )
                    if callback_req_id:
                        await runtime["client"].reply_markdown(callback_req_id, reply)
                    else:
                        await runtime["client"].send_markdown(target, reply)
            elif callback_req_id:
                try:
                    await runtime["client"].reply_markdown(callback_req_id, reply)
                    _LOGGER.info("Replied by callback req_id=%s", callback_req_id)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Reply by callback failed, fallback to active send: %r", err
                    )
                    await runtime["client"].send_markdown(target, reply)
            else:
                await runtime["client"].send_markdown(target, reply)
            _LOGGER.info("Reply delivered to %s", target)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed handling inbound message: %r | frame=%s", err, frame)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WeCom Notify from config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = WeComWsClient(hass, entry.data[CONF_BOT_ID], entry.data[CONF_SECRET])
    selected_agent = entry.options.get(CONF_AGENT_ID, entry.data.get(CONF_AGENT_ID))
    if not selected_agent:
        selected_agent = await _get_preferred_agent_id(hass)

    runtime: dict[str, Any] = {
        "client": client,
        "agent_id": selected_agent,
        "paired_targets": set(),
    }
    _LOGGER.info(
        "WeCom conversation agent: %s",
        runtime.get("agent_id") or "default (no preferred agent found)",
    )

    async def _update_listener(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        await hass.config_entries.async_reload(updated_entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_update_listener))

    client.set_message_callback(lambda frame: _handle_inbound(hass, runtime, frame))
    await client.start()

    hass.data[DOMAIN][entry.entry_id] = runtime

    async def handle_send_message(call: ServiceCall) -> None:
        await _handle_send_message(hass, call)

    async def handle_test_conversation(call: ServiceCall) -> None:
        text = call.data.get(ATTR_TEXT, "")
        if not text:
            return
        reply = await _ask_home_assistant(hass, text, "test", runtime.get("agent_id"))
        _LOGGER.info("Conversation test input=%s reply=%s", text, reply)

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            handle_send_message,
            schema=SERVICE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_TEST_CONVERSATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TEST_CONVERSATION,
            handle_test_conversation,
            schema=vol.Schema({vol.Required(ATTR_TEXT): cv.string}),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    runtime = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime is not None:
        await runtime["client"].stop()

    if not hass.data.get(DOMAIN):
        if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
            hass.services.async_remove(DOMAIN, SERVICE_SEND_MESSAGE)
        if hass.services.has_service(DOMAIN, SERVICE_TEST_CONVERSATION):
            hass.services.async_remove(DOMAIN, SERVICE_TEST_CONVERSATION)

    return unload_ok
