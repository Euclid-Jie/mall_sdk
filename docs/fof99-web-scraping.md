# FOF99 网页净值抓取说明

本文记录如何不通过官方 SDK、直接复用 `mp.fof99.com` 基金详情页背后的网页接口抓取净值数据。

项目约定：`fof99/` 是供应商 SDK 目录，网页抓取能力放在项目根目录 `scraper.py`，不要放进 `fof99/`。

## 适用场景

官方 SDK 有调用次数限制，或者需要抓取网页详情页已经展示的净值表时，可以使用本方法。

该方法不需要每次打开浏览器，但需要有效的 FOF99 网页登录 token。token 默认从环境变量或项目根目录 `.env` 读取。

## 已验证页面

```text
https://mp.fof99.com/fund/view/1efcf35e914e1b54
```

页面中“净值分析”表格对应接口：

```text
GET https://api.huofuniu.com/newgoapi/fund/priceList
```

## 请求参数

```text
token=<网页登录 token>
fid=1efcf35e914e1b54
source=2
order=1
page=1
pagesize=500
```

说明：

- `fid` 来自基金详情页 URL：`/fund/view/{fid}`。
- `source=2` 对应当前页面展示的团队/公司净值来源。
- `order=1` 为按日期倒序，和页面显示一致。
- `page/pagesize` 用于分页；`scraper.py` 会自动翻页直到取完 `total`。

## 字段映射

```text
pd  -> date            日期
pn  -> unit_nav        单位净值
cnw -> cumulative_nav  累计净值
cn  -> adjusted_nav    复权净值
pc  -> change_pct      涨跌幅
```

接口返回的 `pc` 是小数形式，例如 `0.001183432`。`scraper.py` 会转换为百分点，即 `0.1183432`。

## Token 配置

推荐在项目根目录 `.env` 中配置：

```dotenv
FOF99_WEB_TOKEN = your-web-token
```

读取顺序：

1. 显式传入 `FOF99WebScraper(token=...)`
2. 环境变量 `FOF99_WEB_TOKEN`
3. 项目根目录 `.env`

`.env` 已加入 `.gitignore`，不要提交。

## Python 用法

```python
from scraper import FOF99WebScraper

scraper = FOF99WebScraper()
df = scraper.get_fund_nav("1efcf35e914e1b54")
print(df.head())
```

也可以直接传 URL 中的 `fid`：

```python
df = scraper.get_fund_nav("1efcf35e914e1b54", page_size=500)
```

## 命令行用法

```powershell
.\.venv\Scripts\python.exe examples\scrape_fund_nav.py https://mp.fof99.com/fund/view/1efcf35e914e1b54
```

输出前 20 行净值，并打印总行数。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -c "from scraper import FOF99WebScraper; df=FOF99WebScraper().get_fund_nav('1efcf35e914e1b54'); print(len(df)); print(df.head())"
```

当前已验证该基金返回 198 行，最新一行：

```text
date=2026-06-26
unit_nav=1.692
cumulative_nav=1.824
adjusted_nav=1.8659808
change_pct=0.1183432
```
