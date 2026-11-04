import time
import requests
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Sequence
from hashlib import md5
import pandas as pd

try:
    from .fof99 import (
        PersonalFundPrice,
        FundInfo,
        FundPrice,
        FundCompanyPrice,
        GmFundPrice,
        FundMultiCompanyPrice,
        FundMultiPrice,
        CompanyInfo,
    )
    from .scraper import get_fof99_web_token
except ImportError:
    from fof99 import (
        PersonalFundPrice,
        FundInfo,
        FundPrice,
        FundCompanyPrice,
        GmFundPrice,
        FundMultiCompanyPrice,
        FundMultiPrice,
        CompanyInfo,
    )
    from scraper import get_fof99_web_token


# 拒收原因中命中这些关键词时，视为「预期内的拒收」（数据不上传，但不算失败）
DEFAULT_SKIP_REASONS = ("非交易日",)


def _concat_frames(parts: list[pd.DataFrame], template: pd.DataFrame) -> pd.DataFrame:
    """拼接多个分片；全空时返回 template（保证列一致）。"""
    return pd.concat(parts, ignore_index=False) if parts else template


@dataclass
class NavUploadReport:
    """净值批量上传结果。

    Attributes:
        chunks: 各批次 API 原始返回，便于排查。
        uploaded: 实际上传成功的净值行。
        skipped: 被火富牛拒收且命中 `skip_reasons` 的净值行，附加一列 `拒收原因`。
            调用方应把它们标记为已处理，否则每次运行都会重复读到同一批数据、
            而且永远推不上去。
        failed: 被火富牛拒收但原因**不在** `skip_reasons` 的净值行，附加一列
            `拒收原因`。这些行平台没有收下，**不能**标记为已处理——
            要么修数据，要么把它们加进 `skip_reasons`。
    """

    chunks: list[dict] = field(default_factory=list)
    uploaded: pd.DataFrame = field(default_factory=pd.DataFrame)
    skipped: pd.DataFrame = field(default_factory=pd.DataFrame)
    failed: pd.DataFrame = field(default_factory=pd.DataFrame)


class NavUploadPartialFailure(RuntimeError):
    """部分产品被非预期拒收（其余产品/批次已上传成功）。

    抛出时 `report.uploaded` / `report.skipped` 里的行**已经传到平台**了。
    如果调用方传了 `on_chunk`，这些行也已经回写，所以重跑**不会**重传它们；
    只有 `report.failed` 里的行会在下次运行被重新捞出来。
    """

    def __init__(self, report: NavUploadReport):
        self.report = report
        failed = report.failed
        details = [
            f"{code}: {reason}（{count} 条净值）"
            for (code, reason), count in failed.groupby(
                ["产品代码", "拒收原因"], sort=False
            )
            .size()
            .items()
        ]
        super().__init__(
            "FOF99净值上传部分失败（非预期拒收；其余行已上传，"
            "若调用方按 on_chunk 回写则重跑只会重传下面这些）：\n  "
            + "\n  ".join(details)
        )


class FOF99ApiError(RuntimeError):
    """FOF99 网页接口请求失败或返回体不符合预期。"""


class FOF99CompanyNotFound(FOF99ApiError):
    """FOF99 未收录目标管理人（含已注销管理人）。"""


class FOF99Api:
    WEB_API_BASE = "https://api.huofuniu.com"
    WEB_BASE_URL = "https://mp.fof99.com"
    WEB_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )

    def __init__(
        self,
        appid: str = "",
        appkey: str = "",
        token: str = "",
        timeout: int = 30,
    ):
        self.appid = appid
        self.appkey = appkey
        self.token = token
        self.timeout = timeout

    def _get_web_token(self) -> str:
        token = self.token or get_fof99_web_token()
        if not token:
            raise ValueError("请在 FOF99Api(token=...) 或 .env 中配置 FOF99_WEB_TOKEN")
        return token

    def _web_headers(self, referer: str = "/") -> dict:
        """构造 api.huofuniu.com 网页接口的请求头。

        注意：这些接口除 token 外还按 User-Agent 过滤请求。使用 requests 默认
        UA（``python-requests/x.y``）、空 UA 或缺少 UA 时，接口仍返回
        HTTP 200 且 ``error_code=0``，但 ``data`` 为 ``null``，看起来像「没有数据」。
        所以只带 ``access-token`` 是不够的，必须显式带浏览器 UA。
        鉴权本身只依赖查询参数 ``token``；``access-token`` 头仅为兼容保留。
        """
        if not referer.startswith("http"):
            referer = f"{self.WEB_BASE_URL}{referer}"
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.WEB_BASE_URL,
            "Referer": referer,
            "User-Agent": self.WEB_USER_AGENT,
            "access-token": self._get_web_token(),
        }

    @staticmethod
    def _parse_web_payload(res: requests.Response, action: str) -> dict:
        """统一校验网页接口返回体，避免把失败当成「查不到数据」。"""
        res.raise_for_status()
        try:
            payload = res.json()
        except ValueError as exc:
            raise FOF99ApiError(
                f"{action}失败: API 响应不是有效的 JSON（{res.text[:200]!r}）"
            ) from exc
        if not isinstance(payload, dict):
            raise FOF99ApiError(f"{action}失败: API 响应必须是 JSON 对象")
        error_code = payload.get("error_code")
        if error_code != 0:
            raise FOF99ApiError(
                f"{action}失败: error_code={error_code}, msg={payload.get('msg')!r}"
                "；error_code=-4 表示 token 缺失或失效，请更新 FOF99_WEB_TOKEN"
            )
        return payload
    @staticmethod
    def _parse_fund_view_id(fid_or_url: str) -> str:
        fid_or_url = str(fid_or_url).strip()
        if "/fund/view/" in fid_or_url:
            return (
                fid_or_url.split("/fund/view/", 1)[1].split("?", 1)[0].split("#", 1)[0]
            )
        return fid_or_url

    def get_fund_basic_info_from_id(self, fid_or_url: str) -> dict:
        """
        通过 FOF99 网页基金 ID 获取基金基本信息。

        参数可以传基金 ID，也可以传完整详情页 URL，例如：
        https://mp.fof99.com/fund/view/1efcf35e914e1b54

        Returns:
            dict: 包含产品名称、备案编号、公司管理规模等字段。
        """
        fid = self._parse_fund_view_id(fid_or_url)
        url = f"{self.WEB_API_BASE}/newgoapi/funds/analyze"
        res = requests.get(
            url,
            params={
                "token": self._get_web_token(),
                "id": fid,
                "url": "",
            },
            headers=self._web_headers(f"/fund/view/{fid}"),
            timeout=self.timeout,
        )
        payload = self._parse_web_payload(res, "获取基金基本信息")
        data = payload.get("data") or {}
        if not data:
            raise FOF99ApiError(
                f"获取基金基本信息失败: 接口未返回数据（fid={fid}），"
                "请检查 token 是否有效或 User-Agent 是否被拦截"
            )
        return {
            "产品名称": data.get("fund_short_name") or data.get("fund_name"),
            "产品全称": data.get("fund_name"),
            "备案编号": data.get("register_number"),
            "公司管理规模": data.get("scale"),
            "管理人": data.get("advisor"),
            "fid": data.get("id") or fid,
            "company_id": data.get("company_id"),
        }

    @staticmethod
    def _parse_fail_item(item) -> tuple[str, str]:
        """拆出火富牛拒收明细里的 (产品名, 原因)，形如「睦沣一号:非交易日，无法上传净值」。"""
        text = str(item)
        for sep in (":", "："):
            if sep in text:
                name, _, reason = text.partition(sep)
                return name.strip(), reason.strip()
        return text.strip(), ""

    @classmethod
    def _payload_error(
        cls, payload: dict, expected_count: int, extra_hint: str = ""
    ) -> RuntimeError:
        """把不达预期的响应体统一构造成 RuntimeError。"""
        data = payload.get("data")
        fail = data.get("fail") if isinstance(data, dict) else None
        success = data.get("success") if isinstance(data, dict) else None
        success_count = len(success) if isinstance(success, list) else 0
        return RuntimeError(
            "FOF99净值上传失败: "
            f"error_code={payload.get('error_code')}, msg={payload.get('msg')!r}, "
            f"fail={fail!r}, success_count={success_count}, "
            f"expected_count={expected_count}{extra_hint}"
        )

    def _post_raw(
        self,
        update_nav_data_list: list[dict],
        type: Literal["inner", "company"] = "company",
    ) -> dict:
        """发送请求并解析 JSON，**不做业务校验**（error_code 由调用方判断）。"""
        sign = md5(
            f"app_id={self.appid}&tm={int(time.time())}{self.appkey}".encode()
        ).hexdigest()
        url = f"https://mallapi.huofuniu.com/{type}_price/batch/add?app_id={self.appid}&sign={sign}&tm={int(time.time())}"
        res = requests.post(
            url,
            json={
                "price_data": update_nav_data_list,
            },
        )
        print(res.text)
        res.raise_for_status()
        try:
            payload = res.json()
        except ValueError as exc:
            raise RuntimeError("FOF99净值上传失败: API 响应不是有效的 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("FOF99净值上传失败: API 响应必须是 JSON 对象")
        return payload

    def _post_nav_data_list(
        self,
        update_nav_data_list: list[dict],
        type: Literal["inner", "company"] = "company",
    ) -> dict:
        """发送并保证拿到 `error_code == 0` 且 `data` 是对象的响应。"""
        payload = self._post_raw(update_nav_data_list, type)
        if payload.get("error_code") != 0 or not isinstance(payload.get("data"), dict):
            raise self._payload_error(payload, len(update_nav_data_list))
        return payload

    def _update_nav_data_list_to_FOF99(
        self,
        update_nav_data_list: list[dict],
        type: Literal["inner", "company"] = "company",
    ) -> dict:
        """上传并校验：只要有一个产品被拒就报错（不做任何剔除）。"""
        payload = self._post_nav_data_list(update_nav_data_list, type)
        data = payload["data"]
        success = data.get("success")
        fail = data.get("fail")
        expected_count = len(update_nav_data_list)
        success_count = len(success) if isinstance(success, list) else 0
        if bool(fail) or not isinstance(success, list) or success_count != expected_count:
            raise self._payload_error(payload, expected_count)
        return payload

    @staticmethod
    def generate_nav_data_list(sub_nav_data_df: pd.DataFrame) -> list[dict]:
        # 挨个产品添加
        product_code_list = sub_nav_data_df["产品代码"].unique()
        update_nav_data_list = []
        for code in product_code_list:
            single_nav_data = sub_nav_data_df[sub_nav_data_df["产品代码"] == code]
            result = [
                {
                    "date": row["日期"],
                    "price": str(row["单位净值"]),
                    "cumulative_nav_withdrawal": str(row["累计净值"]),
                }
                for _, row in single_nav_data.iterrows()
            ]
            update_nav_data_list.append(
                {
                    "code": code,
                    "nets": result,
                }
            )
        return update_nav_data_list

    @staticmethod
    def _normalize_name(name) -> str:
        """把产品名规范化，用于把平台回的「产品名」对到表里的行。

        只去掉不影响区分度的通称/份额后缀，例如：
        「凯丰凌风2号量化CTA私募证券投资基金（B类份额）」→「凯丰凌风2号量化CTAB」
        「凯丰凌风2号量化CTAB类」（平台回包）→「凯丰凌风2号量化CTAB」
        两者相等，于是无需任何额外请求就能归因。
        """
        text = str(name).strip().replace("（", "(").replace("）", ")")
        for token in (
            "私募证券投资基金",
            "私募投资基金",
            "证券投资基金",
            "私募基金",
            "类份额",
            "份额",
            "基金",
            "(",
            ")",
            " ",
            "　",
        ):
            text = text.replace(token, "")
        return text.rstrip("类")

    @classmethod
    def _name_index(cls, nav_df: pd.DataFrame, name_col: str) -> dict[str, str]:
        """产品代码 -> 规范化产品名，用于把平台回包里的产品名反推到代码。"""
        unique = nav_df.drop_duplicates("产品代码")
        return {
            code: cls._normalize_name(name)
            for code, name in zip(unique["产品代码"], unique[name_col])
        }

    @classmethod
    def _resolve_name(cls, name, normalized: dict[str, str]) -> Optional[str]:
        """把一个平台侧产品名对回代码；对不上或对上多个（同名撞车）时返回 None。"""
        target = cls._normalize_name(name)
        if not target:
            return None
        exact = [code for code, norm in normalized.items() if norm == target]
        if len(exact) == 1:
            return exact[0]
        if not exact and len(target) >= 4:
            prefix = [
                code
                for code, norm in normalized.items()
                if norm.startswith(target) or target.startswith(norm)
            ]
            if len(prefix) == 1:
                return prefix[0]
        return None

    @classmethod
    def _match_names_to_codes(
        cls, names: Sequence, nav_df: pd.DataFrame, name_col: Optional[str]
    ) -> tuple[set[str], list[str]]:
        """把一批平台侧产品名反推到代码，**不产生任何请求**。

        Returns:
            (命中的代码集合, 未能归因的名字列表)
        """
        if not name_col or name_col not in nav_df.columns:
            return set(), [str(name) for name in names]
        normalized = cls._name_index(nav_df, name_col)
        matched: set[str] = set()
        unmatched: list[str] = []
        for name in names:
            code = cls._resolve_name(name, normalized)
            if code is None:
                unmatched.append(str(name))
            else:
                matched.add(code)
        return matched, unmatched

    @classmethod
    def _match_fail_codes(
        cls, fail_entries: Sequence, nav_df: pd.DataFrame, name_col: Optional[str]
    ) -> tuple[dict[str, str], list[str]]:
        """把平台的「产品名:原因」反推到产品代码，**不产生任何请求**。

        Returns:
            (code -> 原因, 未能归因的 fail 原文列表)
        """
        parsed = [cls._parse_fail_item(item) for item in fail_entries]
        if not name_col or name_col not in nav_df.columns:
            return {}, [
                f"{name}:{reason}" if reason else str(name) for name, reason in parsed
            ]
        normalized = cls._name_index(nav_df, name_col)
        matched: dict[str, str] = {}
        unmatched: list[str] = []
        for name, reason in parsed:
            code = cls._resolve_name(name, normalized)
            if code is None:
                unmatched.append(f"{name}:{reason}" if reason else str(name))
            else:
                matched[code] = reason
        return matched, unmatched

    @classmethod
    def _should_isolate(cls, payload: dict, skip_reasons: Sequence[str]) -> bool:
        """整批回包是否值得拆成单产品重传来定位。

        - `data.fail` 非空：产品级拒收，但应由「名字归因」先处理，只有归因失败才值得重传；
        - `error_code` 非 0 但原因命中 `skip_reasons`（如「睦沣一号:非交易日…」）：定位后能跳过；
        - 其余（签名错、app_id 无效、代码不存在等）：直接报错，不值得打 N 次请求。
        """
        data = payload.get("data")
        if isinstance(data, dict) and data.get("fail"):
            return True
        if payload.get("error_code") == 0:
            return False
        reason = cls._parse_fail_item(payload.get("msg"))[1] or str(payload.get("msg"))
        return any(key in reason for key in skip_reasons)

    def _isolate_failed_products(
        self,
        sub_nav_data_df: pd.DataFrame,
        type: Literal["inner", "company"],
        skip_reasons: Sequence[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """逐个产品重传，把「哪个产品被拒、因为什么」锛定到代码级别。

        火富牛的 fail 明细只给出平台侧产品名（与邮件/上游表里的名称不一定一致），
        无法可靠反推到代码，所以用「一产品一请求」来清除这个歧义。

        单产品请求的拒收有两种形态（都已实测遇到）：
        - `{"error_code": 0, "data": {"fail": ["产品名:原因"], "success": []}}`
        - `{"error_code": 10001, "msg": "产品名:原因", "data": null}`
        两种都能归因到本请求唯一的那只产品。

        Returns:
            (uploaded, skipped, failed)，后两者带 `拒收原因` 列。failed 是「平台
            没收下、且原因不在 skip_reasons」的行，调用方**不得**把它们标记为已处理。
        """
        uploaded, skipped, failed = [], [], []
        for _, group in sub_nav_data_df.groupby("产品代码", sort=False):
            payload = self._post_raw(self.generate_nav_data_list(group), type)
            data = payload.get("data")
            fail = data.get("fail") if isinstance(data, dict) else None
            if payload.get("error_code") == 0 and not fail:
                uploaded.append(group)
                continue
            if payload.get("error_code") == 0:
                reasons = []
                for item in fail:
                    _, reason = self._parse_fail_item(item)
                    reason = reason or str(item)
                    if reason not in reasons:
                        reasons.append(reason)
            else:
                # error_code 非 0 时原因在 msg 里，整个请求只有一只产品，仍可归因
                reasons = [
                    self._parse_fail_item(payload.get("msg"))[1]
                    or str(payload.get("msg") or payload)
                ]
            reason_text = "；".join(reasons)
            if any(key in reason_text for key in skip_reasons):
                skipped.append(group.assign(拒收原因=reason_text))
            else:
                failed.append(group.assign(拒收原因=reason_text))

        empty = sub_nav_data_df.iloc[0:0].copy()
        empty_rejected = empty.assign(拒收原因=pd.Series(dtype=object))
        return (
            pd.concat(uploaded) if uploaded else empty,
            pd.concat(skipped) if skipped else empty_rejected,
            pd.concat(failed) if failed else empty_rejected,
        )

    def update_nav_to_FOF99(
        self,
        nav_data_for_update: pd.DataFrame,
        type: Literal["inner", "company"] = "company",
        *,
        isolate_failed: bool = False,
        skip_reasons: Sequence[str] = DEFAULT_SKIP_REASONS,
        name_col: Optional[str] = "产品名称",
        on_chunk: Optional[Callable[[NavUploadReport], None]] = None,
    ) -> NavUploadReport:
        """
        转换数据格式并上传到FOF99。

        火富牛按产品维度返回成败（`data.fail` 是「产品名:原因」列表），
        而**只要有一个产品被拒，整批就不算成功**。处理策略（按请求次数从省到贵）：

        1. **名字归因（默认，零额外请求）**：用 `data.fail` 里的产品名，
           经 `_normalize_name` 规范化后直接对到 `name_col` 列，得到拒收的产品代码。
           既然成功与拒收的总数能对上（平台已收下成功那些），就不必重传，
           只把拒收行计入 `skipped` / `failed`。
           fail 侧归不出来时，再用 `data.success` 里的产品名归因（同样零请求）——
           **只有平台确认收下的产品才会进 `uploaded`**，绝不会误标没传上去的行。
        2. **逐产品重传（`isolate_failed=True`，默认关闭）**：名字归因不了时才用，
           需要额外 N 次请求（N = 本批产品数），会消耗接口额度。
        3. 若两者都不适用，直接报错并原样附上平台回包。

        进度不回滚：每批一有结论就调 `on_chunk`，即使后面某批出现非预期拒收（错在最后
        汇总抛出 `NavUploadPartialFailure`），已经上传成功的行也不会丢标记。
        这是防止「上传成功但 sync_at 未回写 → 下次运行重传一遍、白烧接口额度」的关键。

        Args:
            nav_data_for_update: 含 [产品代码, 日期, 单位净值, 累计净值] 的净值数据。
            type: 上传接口类型，inner / company。
            isolate_failed: 名字归因失败时是否逐产品重传定位（费额度，默认关闭）。
            skip_reasons: 拒收原因包含其中任一关键词时就「不计为失败」。
            name_col: 用于归因的产品名列；表里没有该列时自动退化为无归因。
            on_chunk: 每批结论的回调，参数是本批的 `NavUploadReport`（单批）。
                调用方应在里面**立即落库**回写 `uploaded` / `skipped` 行，
                这样部分失败时已上传进度也不会丢。

        Returns:
            NavUploadReport: uploaded 为已上传成功的行；skipped 为被跳过（预期内拒收）
            的行（含 `拒收原因` 列），**调用方应将其标记为已处理**；failed 为被拒收但原因不在 skip_reasons 的行，平台没收下，**不得**标记为已处理。
            传空表时返回空报告、不发起任何请求。

        Raises:
            NavUploadPartialFailure: 有非预期拒收（已上传行仍然有效，见 `report.failed`）。
            RuntimeError: 整批硬失败（签名错/app_id 无效等），此时本批没有行可回写。
        """
        if name_col is not None and name_col not in nav_data_for_update.columns:
            name_col = None
        # 防止修改原数据
        nav_data_for_update = nav_data_for_update.copy()
        # 没有待上传数据是正常状态（例如全部被清洗规则剔除），不是错误：
        # 返回空报告，不发任何请求。
        if nav_data_for_update.shape[0] == 0:
            return NavUploadReport(
                chunks=[],
                uploaded=nav_data_for_update,
                skipped=nav_data_for_update,
            )
        # 确认字段
        expected_columns = ["产品代码", "日期", "单位净值", "累计净值"]
        assert set(nav_data_for_update.columns) >= set(
            expected_columns
        ), "字段不匹配，请检查！期望字段: {}，实际字段: {}".format(
            expected_columns, nav_data_for_update.columns.tolist()
        )
        # 日期格式转换
        assert (
            nav_data_for_update["日期"].dtype == "datetime64[ns]"
        ), "日期格式错误，请检查！"
        nav_data_for_update["日期"] = nav_data_for_update["日期"].dt.strftime(
            "%Y-%m-%d"
        )

        chunks: list[dict] = []
        uploaded_parts: list[pd.DataFrame] = []
        skipped_parts: list[pd.DataFrame] = []
        failed_parts: list[pd.DataFrame] = []
        # 分多个chunk上传
        for i in range(0, nav_data_for_update.shape[0], 1000):
            sub_nav_data_df = nav_data_for_update.iloc[i : i + 1000, :]
            chunk_report = self._upload_chunk(
                sub_nav_data_df,
                type,
                isolate_failed=isolate_failed,
                skip_reasons=skip_reasons,
                name_col=name_col,
            )
            chunks.extend(chunk_report.chunks)
            uploaded_parts.append(chunk_report.uploaded)
            skipped_parts.append(chunk_report.skipped)
            failed_parts.append(chunk_report.failed)
            # 本批一有结论就立刻交给调用方落库：后面某批硬失败也不会丢掉这里的进度
            if on_chunk is not None:
                on_chunk(chunk_report)

        empty = nav_data_for_update.iloc[0:0].copy()
        empty_rejected = empty.assign(拒收原因=pd.Series(dtype=object))
        report = NavUploadReport(
            chunks=chunks,
            uploaded=_concat_frames(uploaded_parts, empty),
            skipped=_concat_frames(skipped_parts, empty_rejected),
            failed=_concat_frames(failed_parts, empty_rejected),
        )
        if not report.failed.empty:
            # 注意：uploaded / skipped 里的行平台已经收下了（on_chunk 也已回写），
            # 只有 failed 里的行需要调用方处理，所以这里不要把它们也退回去。
            raise NavUploadPartialFailure(report)
        return report

    def _upload_chunk(
        self,
        sub_nav_data_df: pd.DataFrame,
        type: Literal["inner", "company"],
        *,
        isolate_failed: bool,
        skip_reasons: Sequence[str],
        name_col: Optional[str],
    ) -> NavUploadReport:
        """上传一批（≤1000 行）并定位被拒产品；**不因产品级拒收而中断**。"""
        update_nav_data_list = self.generate_nav_data_list(sub_nav_data_df)
        payload = self._post_raw(update_nav_data_list, type)
        expected_count = len(update_nav_data_list)
        data = payload.get("data")
        fail = data.get("fail") if isinstance(data, dict) else None
        success = data.get("success") if isinstance(data, dict) else None
        success_count = len(success) if isinstance(success, list) else 0
        empty = sub_nav_data_df.iloc[0:0].copy()
        empty_rejected = empty.assign(拒收原因=pd.Series(dtype=object))

        # ① 整批成功：零额外请求
        if (
            payload.get("error_code") == 0
            and not fail
            and success_count == expected_count
        ):
            return NavUploadReport(
                chunks=[payload],
                uploaded=sub_nav_data_df,
                skipped=empty_rejected,
                failed=empty_rejected,
            )

        # ② 零额外请求的路径：用平台回的产品名在本地归因到代码。
        # 成功/拒收总数能对上，就说明每个产品都已得到结论（成功的平台已收下），
        # 因此只需剔除被拒收的行，不必重传。
        if fail and success_count + len(fail) == expected_count:
            resolved = self._split_by_names(
                sub_nav_data_df, success or [], fail, name_col, skip_reasons
            )
            if resolved is not None:
                uploaded_part, skipped_part, failed_part = resolved
                print(
                    f"本批 {len(fail)} 个产品被拒，已按产品名归因到代码（无额外请求）："
                    f"跳过 {sorted(skipped_part['产品代码'].unique().tolist())}"
                    + (
                        f"；需处理 {sorted(failed_part['产品代码'].unique().tolist())}"
                        if not failed_part.empty
                        else ""
                    )
                )
                return NavUploadReport(
                    chunks=[payload],
                    uploaded=uploaded_part,
                    skipped=skipped_part,
                    failed=failed_part,
                )

        # ③ 逐产品重传定位（费额度）或直接报错：整批硬失败时本批没有任何行可回写
        product_level = bool(fail) or self._should_isolate(payload, skip_reasons)
        if not isolate_failed or not product_level:
            raise self._payload_error(payload, expected_count)
        print(
            f"该批有拒收（fail={fail!r}），逐个产品重传以定位原因"
            f"（本批 {expected_count} 个产品，需要 {expected_count} 次请求）…"
        )
        up, skipped, failed = self._isolate_failed_products(
            sub_nav_data_df, type, skip_reasons
        )
        return NavUploadReport(
            chunks=[payload], uploaded=up, skipped=skipped, failed=failed
        )

    @classmethod
    def _split_by_names(
        cls,
        nav_df: pd.DataFrame,
        success: Sequence,
        fail: Sequence,
        name_col: Optional[str],
        skip_reasons: Sequence[str],
    ) -> Optional[tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]:
        """只用平台回包里的产品名，把本批行拆成 (已上传, 预期内拒收, 非预期拒收)。

        归因不出来时返回 None（调用方继续走「逐产品重传」或报错）。
        关键性质：**只有平台确认收下的产品才会进 uploaded**，
        所以即使 fail 里的名字对不上代码，也不会误标还没传上去的行。
        """
        empty_rejected = nav_df.iloc[0:0].copy().assign(
            拒收原因=pd.Series(dtype=object)
        )
        codes = nav_df["产品代码"]
        reason_by_code, unmatched_fail = cls._match_fail_codes(fail, nav_df, name_col)
        if reason_by_code and not unmatched_fail:
            # fail 侧全部归因成功：剩下的产品就是平台已收下的
            rejected_mask = codes.isin(set(reason_by_code))
        else:
            # fail 侧归不出来：改从 success 侧归因，宁可少标也不误标
            success_codes, unmatched_success = cls._match_names_to_codes(
                success, nav_df, name_col
            )
            if not success_codes or unmatched_success:
                print(
                    f"⚠️ 有 {len(unmatched_fail)} 个拒收产品名、"
                    f"{len(unmatched_success)} 个成功产品名无法归因："
                    f"{unmatched_fail + unmatched_success}"
                )
                return None
            rejected_mask = ~codes.isin(success_codes)
        uploaded = nav_df[~rejected_mask]
        rejected = nav_df[rejected_mask]
        if rejected.empty:
            return uploaded, empty_rejected, empty_rejected
        reasons = rejected["产品代码"].map(
            lambda code: reason_by_code.get(code) or "平台拒收（原因未能归因）"
        )
        skip_mask = rejected["产品代码"].map(
            lambda code: any(
                key in (reason_by_code.get(code) or "") for key in skip_reasons
            )
        )
        return (
            uploaded,
            rejected[skip_mask].assign(拒收原因=reasons[skip_mask]),
            rejected[~skip_mask].assign(拒收原因=reasons[~skip_mask]),
        )

    def get_fund_info(self, reg_code: str = "SVZ009"):
        req = FundInfo(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code)
        res = req.do_request(use_df=False)
        return res

    def get_fund_price(
        self,
        reg_code: str = "SVZ009",
        start_date: str = "2010-01-01",
    ):
        req = FundPrice(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code=reg_code, start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_person_fund_price(
        self,
        fid: str = "381719",
        start_date: str = "2010-01-01",
    ):
        req = PersonalFundPrice(self.appid, self.appkey)  # 请求对
        req.set_params(fid=fid, start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_company_price(
        self,
        reg_code: str = "JX919A",
        start_date: str = "2010-01-01",
    ):
        req = FundCompanyPrice(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code=reg_code, start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_public_fund_price(
        self,
        reg_code="022461",
        start_date: str = "2010-01-01",
    ) -> pd.DataFrame:
        req = GmFundPrice(self.appid, self.appkey)  # 请求对
        req.set_params(str(reg_code).zfill(6), start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_multi_price(
        self,
        reg_codes: list,
        date: str = None,
    ):
        def chunk_list(lst, chunk_size):
            """Helper function to split a list into chunks."""
            for i in range(0, len(lst), chunk_size):
                yield lst[i : i + chunk_size]

        all_results = []
        for chunk in chunk_list(reg_codes, chunk_size=40):
            req = FundMultiPrice(self.appid, self.appkey)  # 请求对
            req.set_params(
                order="0", order_by="nav", reg_code=",".join(chunk), date_=date
            )
            res = req.do_request(use_df=True)
            all_results.append(res)
        return pd.concat(all_results, ignore_index=True)

    def get_multi_company_price(
        self,
        reg_codes: list,
        date: str = None,
    ):
        def chunk_list(lst, chunk_size):
            """Helper function to split a list into chunks."""
            for i in range(0, len(lst), chunk_size):
                yield lst[i : i + chunk_size]

        all_results = []
        for chunk in chunk_list(reg_codes, chunk_size=40):
            req = FundMultiCompanyPrice(self.appid, self.appkey)  # 请求对
            req.set_params(
                order="0", order_by="nav", reg_code=",".join(chunk), date_=date
            )
            res = req.do_request(use_df=True)
            all_results.append(res)
        return pd.concat(all_results, ignore_index=True)

    def get_company_info_from_code(
        self, comp_code, include_cancelled: bool = True
    ) -> dict:
        """按管理人登记编号（或名称）获取 FOF99 管理人信息。

        FOF99 的 ``company/advancedlist`` 默认只返回正常运作的管理人；已注销的
        管理人（``cancel_date`` 非空）必须用 ``active=-1`` 才能查到。因此这里先查
        正常运作，查不到再回退到 ``active=-1``，避免把已注销管理人或未收录管理人
        误判成 token 失效。

        Raises:
            FOF99CompanyNotFound: FOF99 确实没有收录该管理人。
            FOF99ApiError: 鉴权、网络或返回体异常。
        """
        key_value = str(comp_code).strip()
        if not key_value:
            raise ValueError("comp_code 不能为空")

        company = self._find_company(key_value, active="1")
        if company is None and include_cancelled:
            company = self._find_company(key_value, active="-1")
        if company is None:
            raise FOF99CompanyNotFound(
                f"FOF99 未收录管理人 {key_value}（active=1 与 active=-1 均无结果）"
            )
        return company

    def _find_company(self, key_value: str, active: str) -> dict | None:
        res = requests.get(
            f"{self.WEB_API_BASE}/newgoapi/company/advancedlist",
            params={
                "token": self._get_web_token(),
                "keyValue": key_value,
                "member_type": "不限",
                "fund_num": "-1",
                "scale": "0",
                "found_date": "0",
                "active": active,
                "company_manager_active": "-1",
                "page": "1",
                "pagesize": "20",
                "advise_type": "0",
                "order_by": "fund_num",
                "order": "1",
                "isReport": "0",
            },
            headers=self._web_headers(f"/company/index?keyValue={key_value}"),
            timeout=self.timeout,
        )
        payload = self._parse_web_payload(res, f"查询管理人 {key_value}")
        data = payload.get("data")
        if data is None:
            raise FOF99ApiError(
                f"查询管理人 {key_value} 失败: 接口返回 error_code=0 但 data=null"
                "，通常是 token 失效或 User-Agent 被拦截，而不是没有数据"
            )
        if not isinstance(data, dict):
            raise FOF99ApiError(f"查询管理人 {key_value} 失败: data 格式异常 {data!r}")
        rows = data.get("list") or []
        if not isinstance(rows, list):
            raise FOF99ApiError(
                f"查询管理人 {key_value} 失败: list 格式异常 {rows!r}"
            )
        return self._match_company(rows, key_value)

    @staticmethod
    def _match_company(rows: list[dict], key_value: str) -> dict | None:
        """在返回列表中定位目标管理人；没有精确匹配时返回 None。"""
        if not rows:
            return None
        target = str(key_value).strip()
        target_upper = target.upper()
        for row in rows:
            if str(row.get("register_code") or "").strip().upper() == target_upper:
                return row
        for row in rows:
            names = {
                str(row.get(field) or "").strip()
                for field in ("name_short", "company_name", "name_cn")
            }
            if target in names:
                return row
        return None

    def search_fund(self, keyword: str) -> list:
        res = requests.get(
            f"{self.WEB_API_BASE}/newgoapi/fund/global/search",
            params={"token": self._get_web_token(), "keyValue": keyword},
            headers=self._web_headers("/fund/index"),
            timeout=self.timeout,
        )
        payload = self._parse_web_payload(res, f"搜索基金 {keyword}")
        data = payload.get("data")
        if data is None:
            raise FOF99ApiError(
                f"搜索基金 {keyword} 失败: 接口返回 error_code=0 但 data=null"
                "，通常是 token 失效或 User-Agent 被拦截，而不是没有数据"
            )
        if not isinstance(data, list):
            raise FOF99ApiError(f"搜索基金 {keyword} 失败: data 格式异常 {data!r}")
        return data

    def get_fund_info_from_code(self, registerNo) -> pd.DataFrame:
        """
        通过管理人登记编号获取基金信息

        Returns:
            pd.DataFrame: 包含以下字段的基金信息数据框
            - legal_person_name: 上海高毅投资管理有限公司
            - credit_no: 91310120069360143D
            - business_term: 2013-05-29至2033-05-28
            - business_scope: 资产管理，投资管理。\r\n【依法须经批准的项目，经相关部门批准后方可开展经营活动】
            - register_address: 上海市奉贤区青村镇奉村路458号1幢221室
            - register_code: P1002305
            - name_cn: 上海高毅资产管理合伙企业（有限合伙）
            - name_short: 上海高毅资管
            - strategy: 股票多头
            - scale: 100亿元以上
            - found_date: 2013-05-29
            - fund_num: 370
            - member_type: 普通会员
            - register_capital: 35833
            - paid_capital: 35833
            - main_type: 私募证券投资基金管理人
            - office_address: 广东省深圳市福田区中心四路一号深圳嘉里建设广场3座25层
        """
        #
        req = CompanyInfo(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code=registerNo)
        res = req.do_request(use_df=True)
        return res
