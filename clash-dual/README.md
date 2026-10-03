# 双 clash 进程分流（AI 国外 / 学习通国内）

客户场景：AI 模型接口（OpenAI 等）在海外，学习通与国内搜题题库在国内。
用一个进程管国内外流会互相拖累（AI 慢/超时 或 学习通绕路被风控）。
方案：**两个独立 clash 进程按目标分流**，刷课工具显式绑定 AI 专用代理。

## 架构

```
学习通刷课.exe
 ├── 学习通页面 / 国内搜题 API  ── 直连（不经任何代理）
 └── AI 模型接口（OpenAI 等）  ── http://127.0.0.1:7892  (clash-ai 实例)

clash-cn 实例 (端口 7890)  ── 全部 DIRECT      （可选，默认直连已够）
clash-ai 实例 (端口 7892)  ── 全部走国外节点    （AI 专用）
```

## 使用方法

1. 配置两个 clash 实例：
   - `clash-cn.yaml`：国内直连实例（无需改动）。
   - `clash-ai.yaml`：把 `AI-NODE` 的 `server/port/cipher/password`
     换成你自己的节点；或用订阅（删掉 `proxies` 改 `proxy-providers`）。
2. 启动双进程：
   - Windows：双击 `start-clash-dual.bat`（本目录需有 `mihomo.exe`）。
   - Linux/macOS：`bash start-clash-dual.sh`（`mihomo` 需在 PATH）。
3. 学习通刷课工具 → 设置页 → **AI 代理** 填 `http://127.0.0.1:7892`，
   保存。连接测试会走该代理验证。

## 效果

- AI 请求：固定走 7892 国外节点，绕开 GFW，OpenAI 响应稳定；
- 学习通/题库：全程直连，不绕路、不易触发风控；
- 系统无需开 TUN/全局代理，浏览器等其余程序不受影响。

## 端口冲突

`7890/7892` 被占用时，改对应 yaml 的 `mixed-port`，并把工具里
「AI 代理」同步改成新端口。

## 说明

- 「AI 代理」留空 = 沿用系统环境变量/进程分流（旧行为，不强制）。
- AIAsk 的 curl 兜底同样带 `-x` 走该代理，保证多通道一致。
