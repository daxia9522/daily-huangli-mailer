# daily-huangli-mailer

每天自动生成完整“今日黄历”，并以 **美化 HTML 邮件**发送。

适合放在 **GitHub 公开仓库 + GitHub Actions** 里跑。仓库不保存任何邮箱密码，全部通过 **Actions Secrets / 环境变量** 注入。

## 功能

- 支持每日自动运行
- 生成完整黄历信息：
  - 公历
  - 农历
  - 干支
  - 节气 / 下一节气
  - 节日
  - 冲煞
  - 建除十二神
  - 吉凶等级
  - 吉神 / 凶煞
  - 宜 / 忌
  - 时辰吉凶
- 邮件输出为 **HTML 美化排版**
- 邮件配置走环境变量，适合公开仓库
- 对 Gmail 支持与 TrendRadar 类似的自动识别方式

## 调度说明

使用 GitHub Actions 定时运行，也支持手动触发。

## 仓库结构

```text
.
├── .github/workflows/daily-huangli.yml
├── .env.example
├── main.py
├── requirements.txt
└── README.md
```

## 需要配置的 GitHub Secrets

进入：

`Settings -> Secrets and variables -> Actions`

添加这些 **Secrets**：

### 必填

- `EMAIL_FROM`
  - 发件邮箱
  - 示例：`your_sender_email@example.com`

- `EMAIL_PASSWORD`
  - Gmail App Password
  - **不要带空格**

- `EMAIL_TO`
  - 收件邮箱
  - 示例：`your_receiver_email@example.com`

### 可选

- `EMAIL_FROM_NAME`
  - 发件人显示名
  - 示例：`今日黄历`

- `EMAIL_SUBJECT_PREFIX`
  - 邮件主题前缀
  - 示例：`[GitHub Actions]`

- `EMAIL_SMTP_SERVER`
- `EMAIL_SMTP_PORT`

如果你使用 Gmail，这两个可以留空。脚本会按发件域名自动识别为：

- `smtp.gmail.com:587`

如果你想强制指定，也可以自行填入。

## 本地运行

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 仅生成，不发邮件

```bash
python main.py --save-dir dist
```

### 3. 生成并发送邮件

```bash
export EMAIL_FROM="your_sender_email@example.com"
export EMAIL_PASSWORD="your_email_app_password_without_spaces"
export EMAIL_TO="your_receiver_email@example.com"
python main.py --send-email --save-dir dist
```

## GitHub Actions 工作流

默认 workflow：

- 支持定时自动执行
- 支持 `workflow_dispatch` 手动触发
- 仅发邮件，不上传运行产物

## 输出风格

邮件正文采用 HTML 卡片式布局，重点信息会被清楚拆成区块，适合邮箱直接阅读，不需要再看纯文本长串。

## 致谢

本项目黄历数据能力基于：

- [OPN48/cnlunar](https://github.com/OPN48/cnlunar)

感谢原项目作者与贡献者。
