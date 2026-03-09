# 企业微信

`ha_wecom` 是一个 Home Assistant 自定义集成，用于将企业微信智能机器人接入 HA，实现消息通知与对话联动。

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-china&repository=ha_wecom&category=integration)

## 企业微信侧设置（先完成）

参考官方文档：<https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21657>

### 第一步：以长连接方式创建智能机器人，获取 Bot ID 和 Secret

以下截图按官方文档中的顺序展示：

1. 在企业微信客户端进入「工作台管理台 -> 智能机器人」，进入创建页面。

![步骤 1](docs/images/wecom-setup-1-create-bot.png)

2. 新增机器人并选择 `API` 模式，在接入方式中选择「长连接」。

![步骤 2](docs/images/wecom-setup-3-enter-chat.png)

3. 创建完成后，在详情页获取并保存 `Bot ID` 与 `Secret`（后续在 Home Assistant 配置使用）。

![步骤 3](docs/images/wecom-setup-2-bot-id-secret.png)

## 安装

- 通过上方按钮一键添加到 HACS，或在 HACS 中手动添加仓库 `ha-china/ha_wecom`。
- 安装完成后重启 Home Assistant。

## 配置

- 路径：`设置 -> 设备与服务 -> 添加集成 -> 企业微信`
- 必填参数：
  - `bot_id`
  - `secret`
- 可选参数：
  - `agent_id`（下拉选择 HA 对话代理；不填则使用默认/preferred 代理）

## 功能

- 基于企业微信长连接（WebSocket）实现消息收发。
- 支持连接保活、自动重连与心跳。
- 支持 Home Assistant 主动推送消息到企业微信。
- 支持企业微信入站消息回流 Home Assistant 对话能力。
- 入站回复支持回调链路与 `response_url` 链路。
- 支持处理会话事件（如 `enter_chat`）并发送欢迎消息。
- 提供 `notify` 实体与连接状态传感器，便于在 HA 中统一管理。

## 实体与服务

- 实体：
  - `notify.企业微信`
  - `sensor.连接状态`（`disconnected` / `connected` / `authenticated`）
- 服务：
  - `notify.send_message`（通过 `notify.企业微信` 发送）
  - `ha_wecom.send_message`
  - `ha_wecom.test_conversation`

## 对话链路

- 企业微信文本消息进入后，会调用 Home Assistant 对话接口处理。
- 优先使用 `conversation.async_converse`，并兼容 `conversation.process` / `conversation.ask`。
- 对话结果自动回发企业微信，实现机器人与 Home Assistant 的闭环对话。
