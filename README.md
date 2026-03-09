# 企业微信

`ha_wecom` 是一个 Home Assistant 自定义集成，提供企业微信机器人与 Home Assistant 的双向消息能力。

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-china&repository=ha_wecom&category=integration)

## 功能

- 纯 Python 实现企业微信长连接（WebSocket），无需 Node.js 运行时。
- 支持连接保活、自动重连与心跳，适配长期在线消息收发。
- 支持 Home Assistant 主动推送消息到企业微信。
- 支持企业微信入站消息回流 Home Assistant 对话能力。
- 入站回复支持回调链路与 `response_url` 链路，提升消息回传成功率。
- 支持处理会话事件（如 `enter_chat`）并发送欢迎消息。
- 支持在配置流中选择 Home Assistant 对话代理（`agent_id`）。
- 对话代理选择使用 Home Assistant 原生 selector，与系统可选代理保持一致。
- 未显式指定代理时可使用 Voice Assistant 的 preferred conversation agent。
- 提供标准 notify 实体与域服务，可在自动化、脚本和服务调用中统一使用。

## 对话链路

- 企业微信文本消息进入后，会调用 Home Assistant 对话接口处理。
- 优先使用 `conversation.async_converse`，并兼容 `conversation.process` / `conversation.ask`。
- 对话结果自动回发企业微信，实现机器人与 Home Assistant 的闭环对话。
