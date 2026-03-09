# 企业微信

`ha_wecom` 是一个 Home Assistant 自定义集成，提供企业微信机器人与 Home Assistant 的双向消息能力。

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-china&repository=ha_wecom&category=integration)

## 企业微信侧设置（先完成）

1. 在企业微信管理后台创建「智能机器人」并开启消息回调能力。

![创建机器人](docs/images/wecom-setup-1-create-bot.png)

2. 进入机器人详情页，记录 `Bot ID` 和 `Secret`（稍后在 Home Assistant 配置中使用）。

![获取 Bot ID 和 Secret](docs/images/wecom-setup-2-bot-id-secret.png)

3. 在机器人会话里先完成一次配对/进入会话（触发 `enter_chat`），确保机器人可收发消息。

![进入会话触发配对](docs/images/wecom-setup-3-enter-chat.png)

4. 回到 Home Assistant 添加本集成，填入 `Bot ID`、`Secret`，并在下拉框选择对话代理（LLM Agent）。

![Home Assistant 配置集成](docs/images/wecom-setup-4-ha-config.png)

> 说明：以上图片路径已预留在 `docs/images/`，可直接替换为你的实际截图文件。

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
