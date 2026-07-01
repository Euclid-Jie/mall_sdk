# AGENTS.md

本文件是给后续 coding agent 的项目初始化说明。进入本仓库后，先阅读本文件和 `README.md`。

## 项目定位

`mall_sdk` 是火富牛 / FOF99 数据接口的 Python 项目，包含：

- 供应商官方 SDK：`fof99/`
- 项目自有业务封装：`FOF99Api.py`
- 项目自有网页接口抓取：`scraper.py`
- 示例与文档：`examples/`、`docs/`

## 关键约束

1. 不要随意修改 `fof99/` 目录。
   - 该目录视为供应商 SDK 代码。
   - 项目定制逻辑应放在根目录模块，例如 `FOF99Api.py`、`scraper.py`。
   - 只有用户明确要求升级或修补 SDK 本身时，才修改 `fof99/`。

2. 不要提交密钥。
   - `.env` 存放本地 token，已加入 `.gitignore`。
   - 网页 token 变量名为 `FOF99_WEB_TOKEN`。
   - 代码和文档中的 token 示例必须使用占位符。

3. 保持 Windows / PowerShell 兼容。
   - 用户主要在 Windows 上工作。
   - 文档命令优先使用 PowerShell 写法。
   - PowerShell 中不要使用 bash 风格的 `&&`。

4. 新增项目能力时，优先放到项目根目录或独立文档中。
   - 网页抓取逻辑在 `scraper.py`。
   - 官方 SDK 业务编排在 `FOF99Api.py`。
   - 示例脚本放在 `examples/`。
   - 说明文档放在 `docs/`。

## 运行环境

依赖：

```text
requests
pandas
```

推荐环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 常用验证

语法检查：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m py_compile FOF99Api.py scraper.py examples\scrape_fund_nav.py
Remove-Item Env:\PYTHONDONTWRITEBYTECODE
```

网页净值抓取验证：

```powershell
.\.venv\Scripts\python.exe -c "from scraper import FOF99WebScraper; df=FOF99WebScraper().get_fund_nav('1efcf35e914e1b54'); print(len(df)); print(df.head())"
```

网页基本信息验证：

```powershell
.\.venv\Scripts\python.exe -c "from FOF99Api import FOF99Api; print(FOF99Api().get_fund_basic_info_from_id('https://mp.fof99.com/fund/view/1efcf35e914e1b54'))"
```

## 网页抓取约定

`scraper.py` 的 token 读取顺序：

1. 显式传入 `FOF99WebScraper(token=...)`
2. 环境变量 `FOF99_WEB_TOKEN`
3. 项目根目录 `.env`

`.env` 支持以下格式：

```dotenv
FOF99_WEB_TOKEN = your-web-token
```

净值接口字段映射：

```text
pd  -> date
pn  -> unit_nav
cnw -> cumulative_nav
cn  -> adjusted_nav
pc  -> change_pct，代码中转换为百分点
```

## Git 注意事项

- 开始前先看 `git status --short --branch`。
- `.venv/` 和 `.env` 不应纳入提交。
- 如果存在用户未提交改动，不要回滚；只在当前任务范围内追加或编辑。
- 如果需要 pull，先保护本地未提交改动，再执行 `git pull --ff-only`。
