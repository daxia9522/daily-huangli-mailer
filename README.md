# daily-huangli-mailer

每日生成今日黄历，HTML 邮件发送。GitHub Actions 定时跑；凭据只放 Secrets。

## 内容

公历 / 农历 / 干支、节气与节日、冲煞、建除、黄道、彭祖百忌、胎神、方位、纳音、二十八宿、吉神凶煞、宜忌、时辰吉凶（13 辰）。

## 数据

- 引擎：[`lunar-python`](https://github.com/6tail/lunar-python)（离线，无外部 API）
- 历法 / 宜忌：本地计算，贴近主流万年历
- 时辰：早子 `00:00-00:59` … 夜子 `23:00-23:59`

## Secrets

`Settings → Secrets and variables → Actions`

| Secret | 必填 | 说明 |
| --- | --- | --- |
| `EMAIL_FROM` | 是 | 发件邮箱 |
| `EMAIL_PASSWORD` | 是 | 应用专用密码（无空格） |
| `EMAIL_TO` | 是 | 收件邮箱 |
| `EMAIL_FROM_NAME` | 否 | 默认「今日黄历」 |
| `EMAIL_SUBJECT_PREFIX` | 否 | 主题前缀 |
| `EMAIL_SMTP_SERVER` / `EMAIL_SMTP_PORT` | 否 | 默认识别 Gmail / QQ / 163 / vip.163 / 126 等 |

## 调度

- 定时：由 **Cloudflare Workers Cron** 调用 `workflow_dispatch`（建议 UTC `43 22 * * *` ≈ 北京时间 06:43）
- 本仓库 **不再** 使用 GitHub Actions `schedule`（避免免费队列延迟）
- 手动：Actions → Daily Huangli Mailer → Run workflow；或请求 Worker 的测试路径（若已配置）

## 结构

```text
.github/workflows/daily-huangli.yml
main.py
requirements.txt
test_calendar_smoke.py
.env.example
```

## 致谢

黄历数据基于 [6tail/lunar-python](https://github.com/6tail/lunar-python)（MIT）。
