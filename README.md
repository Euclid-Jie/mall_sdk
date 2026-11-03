# mall_sdk

`mall_sdk` 是一个围绕火富牛 / FOF99 数据接口的 Python 项目。项目包含两类能力：

- `fof99/`：供应商提供的官方 SDK 请求类，用于调用 `mallapi.huofuniu.com`，需要 `appid/appkey` 签名。
- 项目根目录自有代码：封装常用业务调用和网页接口抓取能力，避免直接修改供应商 SDK 目录。

当前重点能力包括基金信息查询、平台/团队净值查询、多基金批量净值查询、净值上传，以及从 `mp.fof99.com` 基金详情页背后的网页接口抓取净值数据。

## 目录结构

```text
.
├── FOF99Api.py                    # 项目自有的官方 SDK 业务封装
├── scraper.py                     # 项目自有的 FOF99 网页接口抓取工具
├── fof99/                         # 供应商 SDK 代码，原则上不要直接修改
├── examples/
│   ├── test.py                    # 官方 SDK 基础示例
│   ├── scrape_fund_nav.py         # 网页净值抓取示例
│   └── examples_fund_nav.csv      # 净值抓取样例输出
├── docs/
│   └── fof99-web-scraping.md      # 网页净值抓取接口说明
├── requirements.txt               # Python 依赖
└── .env                           # 本地密钥配置，不提交 git
```

## 安装

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

依赖很少，目前只有：

```text
requests
pandas
```

## 配置

网页抓取能力默认从项目根目录 `.env` 读取 token：

```dotenv
FOF99_WEB_TOKEN = your-web-token
```

`.env` 已加入 `.gitignore`，不要提交到远程仓库。也可以通过系统环境变量覆盖：

```powershell
$env:FOF99_WEB_TOKEN = "your-web-token"
```

官方 SDK 仍然使用 `appid/appkey`，调用时传给 `FOF99Api`：

```python
from FOF99Api import FOF99Api

api = FOF99Api(appid="your-appid", appkey="your-appkey", token="your-web-token")
```

## 官方 SDK 封装

`FOF99Api.py` 是项目自有封装，内部复用 `fof99/` SDK 请求类。常用方法：

- `get_fund_info(reg_code)`：查询私募基金基本信息。
- `get_fund_price(reg_code, start_date)`：查询平台净值。
- `get_company_price(reg_code, start_date)`：查询团队净值。
- `get_public_fund_price(reg_code, start_date)`：查询公募基金净值。
- `get_multi_price(reg_codes, date)`：批量查询平台净值，每批最多 40 只。
- `get_multi_company_price(reg_codes, date)`：批量查询团队净值，每批最多 40 只。
- `search_fund(keyword)`：通过网页接口搜索基金。
- `get_company_info_from_code(comp_code)`：通过网页接口查询管理人信息。
- `get_fund_info_from_code(registerNo)`：通过管理人登记编号查询管理人/基金相关信息。
- `get_fund_basic_info_from_id(fid_or_url)`：通过 FOF99 网页基金 ID 或详情页 URL 查询产品名称、备案编号、公司管理规模等基本信息。
- `update_nav_to_FOF99(nav_data_for_update, type, *, isolate_failed=False, skip_reasons=("非交易日",), name_col="产品名称")`：上传团队或内部净值，按平台返回的拒收原因剔除预期内的拒收，返回 `NavUploadReport`。

示例：

```python
from FOF99Api import FOF99Api

api = FOF99Api(appid="your-appid", appkey="your-appkey")
df = api.get_fund_price(reg_code="SVZ009", start_date="2024-01-01")
print(df.head())
```

## 净值上传与被拒处理

火富牛**按产品维度返回成败**：`data.success` / `data.fail` 里是平台侧产品名，
而**只要有一个产品被拒，整批就不算成功**。SDK 因此不用本地交易日历，而是**以平台返回的拒收原因作为唯一事实来源**：

```python
report = FOF99Api(appid, appkey).update_nav_to_FOF99(nav_df)
print(len(report.uploaded), len(report.skipped))

# 关键：被拒的行没进平台，调用方必须自行标记为已处理，
# 否则每次运行都会重复读到同一批数据（例如写 sync_at = 哨兵时间）
```

处理流程（**按请求次数从省到贵**）：

1. 整批上传（每 1000 行一批）。全部成功 → 直接返回，**只 1 次请求**。
2. **名字归因（默认，零额外请求）**：`data.fail` 里是平台侧产品名（如 `睦沣一号:非交易日…`），
   经 `_normalize_name` 规范化（去掉 `私募证券投资基金`/`份额`/括号等通称）后，
   直接对到 `name_col`（默认 `产品名称`）列 → 得到被拒的产品代码。
   只要 `success_count + len(fail) == 产品数`（每个产品都有结论），就**不重传**，
   平台已收下成功的那些，本地只把被拒行计入 `skipped`。
3. **逐产品重传（`isolate_failed=True`，默认关闭）**：名字归因不了时才用。
   **代价是额外 N 次请求（N = 本批产品数），会消耗接口额度**，所以默认不开。
4. 两道都不适用 → 直接报错并原样附上平台回包（不白花额度）。

归一化实例（实测）：

| 平台回的产品名 | 表里的列名 | 归一化后 |
|---|---|---|
| `凯丰凌风2号量化CTAB类` | `凯丰凌风2号量化CTA私募证券投资基金（B类份额）` | 都是 `凯丰凌风2号量化CTAB` |
| `睦沣一号` | `睦沣一号私募证券投资基金` | 都是 `睦沣一号` |
| `量派聚核46号` | `量派聚核46号私募证券投资基金A` | 前缀匹配 |

> 归因歧义时（一个名字对上多只产品）不做猜测，直接当「无法归因」处理。
> 席位类/期数后缀不会被归并：`…黎夏指增八号` ≠ `…黎夏指增八号一期`。

参数：

- `skip_reasons`：要一并跳过其它拒收时传入，如 `("非交易日", "净值数据为空")`。
- `isolate_failed=True`：归因不了时逐产品重传（费额度）。
- `name_col`：用于归因的产品名列；表里没有该列时自动退化为无归因。

## 网页净值抓取

官方 SDK 有调用次数限制时，可以使用 `scraper.py` 调用基金详情页背后的网页接口。该方式不消耗官方 SDK 调用次数，但需要有效的网页登录 token。默认抓取会先尝试团队净值，若为空则自动回退到平台净值。

已验证页面：

```text
https://mp.fof99.com/fund/view/1efcf35e914e1b54
```

示例：

```python
from scraper import FOF99WebScraper

scraper = FOF99WebScraper()  # 自动读取 .env 中的 FOF99_WEB_TOKEN
df = scraper.get_fund_nav("1efcf35e914e1b54")
print(df.head())
```

如果需要读取详情页基本信息，可以直接使用 `FOF99Api`：

```python
from FOF99Api import FOF99Api

api = FOF99Api()
info = api.get_fund_basic_info_from_id("https://mp.fof99.com/fund/view/1efcf35e914e1b54")
print(info)
```

命令行：

```powershell
.\.venv\Scripts\python.exe examples\scrape_fund_nav.py https://mp.fof99.com/fund/view/1efcf35e914e1b54
```

该示例脚本会先打印基金基本信息，再抓取净值列表，写入 `examples/examples_fund_nav.csv`，并在控制台显示前 5 行净值样例。

也可以用 `--source` 强制指定净值来源，例如 `--source 1` 抓平台净值，`--source 2` 抓团队/公司净值。

返回字段：

```text
date            日期
unit_nav        单位净值
cumulative_nav  累计净值
adjusted_nav    复权净值
change_pct      涨跌幅，单位为百分点
id              网页接口净值记录 ID
fid             FOF99 网页基金 ID
source          数据来源类型
insert_date     接口记录插入时间
```

更详细的接口说明见 [docs/fof99-web-scraping.md](docs/fof99-web-scraping.md)。

## 开发约定

- `fof99/` 是供应商 SDK 目录，除非明确升级 SDK，否则不要在这里做项目自定义改动。
- 项目自有能力放在根目录模块或 `docs/`、`examples/` 下。
- 密钥和 token 只放在 `.env` 或环境变量中，不写入代码、文档示例或提交记录。
- 修改代码后至少运行语法检查：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m py_compile FOF99Api.py scraper.py examples\scrape_fund_nav.py
Remove-Item Env:\PYTHONDONTWRITEBYTECODE
```

如需验证网页抓取：

```powershell
.\.venv\Scripts\python.exe -c "from scraper import FOF99WebScraper; df=FOF99WebScraper().get_fund_nav('1efcf35e914e1b54'); print(len(df)); print(df.head())"
```

如需验证详情页基本信息：

```powershell
.\.venv\Scripts\python.exe -c "from FOF99Api import FOF99Api; print(FOF99Api().get_fund_basic_info_from_id('https://mp.fof99.com/fund/view/1efcf35e914e1b54'))"
```
