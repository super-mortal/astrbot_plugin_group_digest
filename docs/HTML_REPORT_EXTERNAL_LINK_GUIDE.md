# HTML 报告外链配置指南

> 目标：让群里的报告以**可点击的网页链接**形式发出，而不是图片或文件。

## 1. 先搞清楚机制（三步）

插件的做法非常简单，**它只做前两步，不做第三步**：

| 步骤 | 谁来做 | 说明 |
| :--- | :--- | :--- |
| ① 生成 HTML 文件 | **插件** | 写到「报告储存目录」 |
| ② 拼出访问链接 | **插件** | `外链 Base URL` + 文件相对路径 |
| ③ 让这个目录能被公网访问 | **你自己** | 用 Nginx / Caddy 等 Web 服务器把目录映射到域名 |

**关键认知：这个插件本身不带 Web 服务器。** 它只负责写文件、拼链接，不负责把文件发布出去。

链接的拼装规则是：

```
最终链接 = html_base_url 去除尾部斜杠 + "/" + 文件相对 html_output_dir 的路径
```

举例：`html_output_dir` 是 `/srv/reports`，文件是 `/srv/reports/report_123_20260928_xxx.html`，
`html_base_url` 填 `https://report.example.com`，那么群里的链接就是：

```
https://report.example.com/report_123_20260928_xxx.html
```

## 2. 一个常见误区

> **能不能直接用 AstrBot 的 WebUI 端口（默认 6185）来当公网托管？**

**不能。** AstrBot 的 WebUI 对 `/api` 开头的路径强制校验登录态 JWT，
插件注册的 Web 路由挂在 `/api/plugins/{插件名}/...` 下，群友点开链接只会拿到 `401 未授权`。

所以**必须有自己的 Web 服务器**。

## 3. 插件侧配置（三个字段）

在 WebUI 的插件配置中心操作：

| 配置组 | 字段 | 填什么 |
| :--- | :--- | :--- |
| 基础设置 | **输出格式** | 必须勾选 `html` |
| HTML 设置 | **报告储存目录** | HTML 落盘的**绝对路径**，例如 `/srv/reports`。留空则默认在插件数据目录下的 `self_hosted_html_reports` |
| HTML 设置 | **外链 Base URL** | 你的域名前缀，例如 `https://report.example.com`。**不要带结尾斜杠** |
| HTML 设置 | **仅发送外链** | 开启则只发链接；关闭则同时发送 HTML 文件，链接附在文件说明里 |

> 默认储存目录位置：`<AstrBot数据目录>/plugin_data/astrbot_plugin_group_digest/self_hosted_html_reports`

修改配置后需要在插件管理页重载插件，或重启 AstrBot 才会生效。

## 4. 服务器侧部署

### 方案 A：Caddy（推荐）

Caddy 会自动申请并续期 HTTPS 证书，配置最短。

**安装（Ubuntu / Debian）：**

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo apt update && sudo apt install -y caddy
```

**`/etc/caddy/Caddyfile`：**

```caddyfile
report.example.com {
    root * /srv/reports
    file_server
}
```

```bash
sudo systemctl reload caddy
```

> ⚠️ **不要加 `browse` 参数**。加了会开启目录列表，任何人都能列出你所有报告。
> 不加 `browse` 时，只有知道完整文件名才能访问，而文件名里带随机 ID，无法猜出。

**前置条件**：域名 `report.example.com` 的 A 记录已解析到这台服务器，且 80 / 443 端口开放。

### 方案 B：Nginx

如果服务器上已经有 Nginx，直接在现有配置里加一段：

```nginx
server {
    listen 443 ssl;
    server_name report.example.com;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    root /srv/reports;

    location / {
        try_files $uri =404;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`try_files $uri =404;` 的作用与 Caddy 不加 `browse` 一致：**禁止目录列表**。

## 5. 目录与权限

```bash
sudo mkdir -p /srv/reports
```

确保 **运行 AstrBot 的用户**对 `/srv/reports` 有写权限（插件要往里写文件），
同时 **运行 Web 服务器的用户**（通常是 `caddy` 或 `www-data`）有读权限。

```bash
sudo chown -R <运行AstrBot的用户>:<运行AstrBot的用户> /srv/reports
sudo chmod 755 /srv/reports
```

## 6. Docker 部署注意事项

这是最容易踩坑的地方。**插件看到的路径是容器内的路径，Web 服务器看到的是宿主机的路径，两者必须指向同一个真实目录。**

假设宿主机目录 `/host/astrbot/data` 已经挂载给 AstrBot 容器的 `/AstrBot/data`。

**做法一（推荐）：Caddy 也跑容器，挂载同一个宿主机目录**

```yaml
services:
  caddy:
    image: caddy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /host/astrbot/data/plugin_data/astrbot_plugin_group_digest/self_hosted_html_reports:/srv/reports:ro
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
volumes:
  caddy_data:
```

此时插件侧「报告储存目录」**留空**即可（用默认位置），Caddy 直接读宿主机对应目录。

**做法二：Caddy 跑在宿主机上**

插件侧「报告储存目录」填**宿主机绝对路径**，例如 `/host/astrbot/data/plugin_data/.../self_hosted_html_reports`。

> 注意：如果 AstrBot 容器只挂载了 `./data:/AstrBot/data`，
> 那么容器内 `/AstrBot/data` 就对应宿主机 `./data`，两边是同一个目录，路径换算不要搞错。

## 7. 验证步骤

1. **确认文件写出来了**：在服务器上 `ls -lh <报告储存目录>`，应该能看到 `report_*.html`
2. **确认能直接打开**：`curl -I https://report.example.com/<刚才那个文件名>`
   - 期望 `HTTP/2 200`
   - `404` → 目录映射不对，或文件不在这个目录里
   - `401 / 403` → 撞到了别的服务或权限不对
3. **确认目录列表是关的**：直接访问 `https://report.example.com/`
   - 期望 `403` 或 `404`
   - **如果列出了文件清单，立刻去关掉 `browse` / 加回 `try_files`**

## 8. 安全说明

- 报告文件名包含随机 ID（默认格式带 ULID 或 TraceID），**无法被枚举猜测**
- 这是「**链接保密**」而不是「访问控制」—— 拿到链接的任何人都能看。如果报告内容敏感，
  建议不要开外链，直接用图片/文件形式发送
- **绝对不要**给这个目录开启目录列表，否则等于把全部历史报告公开
- 不要把 `html_output_dir` 指到 AstrBot 的数据根目录或配置目录

## 9. 备用方案：没有公网 Web 服务器时

| 方案 | 说明 | 取舍 |
| :--- | :--- | :--- |
| 对象存储 | 报告生成后上传到腾讯 COS / 阿里 OSS / Cloudflare R2 | 需要额外开发上传逻辑；稳定、无需维护服务器 |
| 内网穿透 | cloudflared / frp 把内网服务暴露出去 | 零成本；地址会变、稳定性差，不适合长期使用 |
| 不用外链 | 直接用图片或 HTML 文件形式发到群里 | 最简单，无需任何服务器 |
