# 学习通刷课 — Linux 版说明

完整文档见 [`学习通刷课/shuake_src/README.md`](../../学习通刷课/shuake_src/README.md)（配置说明 / 驱动下载 / AI 设置），本文件只列 Linux 专属要点。

## 默认浏览器与驱动

- **默认浏览器：Firefox**（未保存配置时自动选择，无需手动设置）
- **默认驱动：geckodriver**，按顺序自动探测：
  1. 项目目录 `学习通刷课/geckodriver/geckodriver`
  2. `/usr/bin`、`/usr/local/bin`、`/snap/bin`
  3. 系统 PATH
  4. Selenium Manager 自动下载

## 驱动安装（任选其一）

```bash
# 方式一：apt 安装（装到 /usr/bin/geckodriver）
sudo apt install firefox-geckodriver

# 方式二：手动下载（版本需与 Firefox 主版本匹配）
# https://github.com/mozilla/geckodriver/releases
tar xzf geckodriver-v0.36.0-linux64.tar.gz
mkdir -p 学习通刷课/geckodriver && mv geckodriver 学习通刷课/geckodriver/
chmod +x 学习通刷课/geckodriver/geckodriver
```

其他浏览器：Chromium 用 `sudo apt install chromium-driver`；Edge 手动下载 msedgedriver linux64 版放入 PATH。

## 启动

```bash
bash 学习通刷课/run_linux.sh             # 源码运行
# 或
bash 学习通刷课/shuake_src/run_local.sh  # 已配置好 .pylibs/.syslib 的机器
```

**版本匹配规则**：驱动主版本号必须等于浏览器主版本号，不匹配时程序日志会打印当前/期望版本与下载链接。
