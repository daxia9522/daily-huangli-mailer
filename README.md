# daily-huangli-mailer

每日生成今日黄历，并以 HTML 邮件发送。可在 GitHub Actions 定时跑；邮箱凭据只放 Secrets，不进仓库。

## 内容

公历 / 农历 / 干支、节气与节日、冲煞、建除、吉凶、方位、胎神、宜忌、吉神凶煞、时辰吉凶。

## GitHub Secrets

`Settings → Secrets and variables → Actions`

| Secret | 必填 | 说明 |
| --- | --- | --- |
| `EMAIL_FROM` | 是 | 发件邮箱（Gmail） |
| `EMAIL_PASSWORD` | 是 | Gmail 应用专用密码（无空格） |
| `EMAIL_TO` | 是 | 收件邮箱 |
| `EMAIL_FROM_NAME` | 否 | 发件显示名，默认可用「今日黄历」 |
| `EMAIL_SUBJECT_PREFIX` | 否 | 主题前缀 |
| `EMAIL_SMTP_SERVER` / `EMAIL_SMTP_PORT` | 否 | 默认 `smtp.gmail.com:587` |

## 调度

- 定时：`43 22 * * *`（UTC）≈ 北京时间次日 06:43
- 手动：Actions → **Daily Huangli Mailer** → Run workflow

## 本地运行

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 仅生成
python main.py --save-dir dist

# 生成并发送
export EMAIL_FROM=... EMAIL_PASSWORD=... EMAIL_TO=...
python main.py --send-email --save-dir dist
```

参考 `.env.example`。

## 结构

```text
.github/workflows/daily-huangli.yml
main.py
requirements.txt
.env.example
```

## 致谢

黄历数据：[OPN48/cnlunar](https://github.com/OPN48/cnlunar)
