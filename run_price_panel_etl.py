# -*- coding: utf-8 -*-
"""比价测算面板 ETL 脚本

该脚本将比价脚本的匹配结果、历史销售聚合表以及订单四张聚合表整合为面板可直接消费的
中间层数据（Parquet/CSV 兜底），并输出运行日志，确保新数据上线流程标准化。

使用方式（示例）：
    python run_price_panel_etl.py --dry-run
    python run_price_panel_etl.py --date 2025-09-26 --verbose

目录约定（默认相对脚本所在文件夹）：
    raw/price_match/         # 原始两店比价输入（可选）
    raw/historical_sales/    # 历史销售聚合 Excel（Sheet1=本店，Sheet2=竞对）
    raw/orders/              # 订单四张聚合 Excel
    reports/                 # 比价脚本输出 matched_products_comparison_final_*.xlsx
    intermediate/            # 本脚本产出的标准化数据（Parquet/CSV）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
REPORT_DIR = BASE_DIR / "reports"
INTERMEDIATE_DIR = BASE_DIR / "intermediate"
LOG_DIR = BASE_DIR / "logs"
# 门店数据-比价看板模块目录（位于测算模型下，供默认回退使用）
PANEL_DATA_DIR = BASE_DIR.parent / "测算模型" / "门店数据" / "比价看板模块"

# 目录兜底创建，保证在手动调用时即便未提前建目录也不会失败
for path in [RAW_DIR, RAW_DIR / "price_match", RAW_DIR / "historical_sales", RAW_DIR / "orders", INTERMEDIATE_DIR, LOG_DIR]:
    path.mkdir(parents=True, exist_ok=True)

PRICE_MATCH_PATTERN = "matched_products_comparison_final_*.xlsx"
HISTORICAL_PATTERN = "*.xlsx"
ORDERS_PATTERN = "*.xlsx"

PANEL_HISTORICAL_PATTERNS = ["历史销售*.xlsx", HISTORICAL_PATTERN]
PANEL_ORDERS_PATTERNS = ["订单数据*.xlsx", ORDERS_PATTERN]

PRICE_MATCH_REQUIRED_SUFFIXES = [
    "商品名称",
    "条码",
    "原价",
    "售价",
    "月售",
    "库存",
]

ORDERS_REQUIRED_COLUMNS = {
    "store_orders": ["商品名称", "店内码", "下单时间", "渠道", "销量", "商品实售价"],
    "store_traffic": ["日期"],
    "product_traffic": ["日期", "商品名称"],
    "cost": ["日期", "商品名称"],
}

HISTORICAL_REQUIRED_COLUMNS = ["商品名称", "条码", "库存", "月售", "售价"]


@dataclass
class ETLResult:
    match_pairs_rows: int = 0
    orders_rows: int = 0
    traffic_rows: int = 0
    historical_rows: int = 0
    warnings: list[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": datetime.now().isoformat(),
            "match_pairs_rows": self.match_pairs_rows,
            "orders_rows": self.orders_rows,
            "traffic_rows": self.traffic_rows,
            "historical_rows": self.historical_rows,
            "warnings": self.warnings or [],
        }


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with stream handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    files = [p for p in directory.glob(pattern) if not p.name.startswith("~$")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def iter_search_candidates(
    preferred_file: Optional[Path],
    search_locations: Iterable[Path],
    patterns: Iterable[str],
) -> Iterable[Path]:
    """Yield concrete file paths to try, respecting explicit path first and fallback directories."""
    if preferred_file:
        preferred_path = Path(preferred_file).expanduser().resolve()
        if preferred_path.is_file():
            yield preferred_path
        else:
            logging.warning("指定文件未找到：%s", preferred_path)
    for location in search_locations:
        loc_path = Path(location).expanduser().resolve()
        if not loc_path.exists():
            continue
        if loc_path.is_file():
            yield loc_path
            continue
        for pattern in patterns:
            candidate = find_latest_file(loc_path, pattern)
            if candidate and not candidate.name.startswith("~$"):
                yield candidate
                break


def _safe_read_excel(path: Path, **kwargs) -> pd.DataFrame:
    logging.info("读取 Excel 文件：%s", path.name)
    try:
        return pd.read_excel(path, **kwargs)
    except FileNotFoundError:
        logging.warning("文件不存在：%s", path)
    except Exception as exc:
        logging.warning("读取 %s 时出错：%s", path, exc)
    return pd.DataFrame()


def _sanitize_numeric(value: object) -> Optional[str]:
    if pd.isna(value):
        return None
    value_str = str(value).strip()
    if not value_str:
        return None
    if value_str.lower().endswith(".0"):
        value_str = value_str[:-2]
    return value_str


def _hash_pair(left: Optional[str], right: Optional[str]) -> str:
    raw = f"{left or ''}|{right or ''}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _generate_match_key(row: pd.Series, store_suffixes: Tuple[str, str]) -> str:
    left_suffix, right_suffix = store_suffixes
    for suffix in (left_suffix, right_suffix):
        barcode = _sanitize_numeric(row.get(f"条码_{suffix}"))
        if barcode:
            return barcode
        store_code = _sanitize_numeric(row.get(f"店内码_{suffix}"))
        if store_code:
            return store_code
    # fallback 到商品名+规格
    name_candidates = []
    specs_candidates = []
    for suffix in store_suffixes:
        for prefix in ("cleaned_商品名称", "商品名称"):
            value = row.get(f"{prefix}_{suffix}")
            if pd.notna(value):
                name_candidates.append(str(value).strip())
        for prefix in ("specs", "规格"):
            value = row.get(f"{prefix}_{suffix}")
            if pd.notna(value):
                specs_candidates.append(str(value).strip())
    base = "|".join(filter(None, ["/".join(sorted(set(name_candidates))).lower(), "/".join(sorted(set(specs_candidates))).lower()]))
    return hashlib.sha1(base.encode("utf-8") if base else b"unknown").hexdigest()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df


def detect_store_suffixes(columns: Iterable[str]) -> Tuple[str, str]:
    suffixes: list[str] = []
    for col in columns:
        if col.startswith("商品名称_"):
            suffixes.append(col[len("商品名称_"):])
    unique_suffixes = list(dict.fromkeys(suffixes))
    if len(unique_suffixes) < 2:
        raise ValueError("匹配结果中无法识别到两个店铺的列，请检查 Excel 表头。")
    return unique_suffixes[0], unique_suffixes[1]


def validate_price_match_columns(df: pd.DataFrame, suffixes: Tuple[str, str]) -> list[str]:
    missing: list[str] = []
    for suffix in suffixes:
        for field in PRICE_MATCH_REQUIRED_SUFFIXES:
            column_name = f"{field}_{suffix}"
            if column_name not in df.columns:
                missing.append(column_name)
    return missing


def load_price_match(
    report_dir: Path,
    preferred_file: Optional[Path] = None,
    extra_dirs: Optional[Iterable[Path]] = None,
) -> Tuple[pd.DataFrame, Optional[Tuple[str, str]], list[str]]:
    warnings: list[str] = []
    report_path: Optional[Path] = None

    if preferred_file:
        preferred_path = Path(preferred_file).expanduser().resolve()
        if preferred_path.is_file():
            report_path = preferred_path
        else:
            warnings.append(f"指定比价文件不存在：{preferred_path}")

    def _pick_from_locations(locations: Iterable[Path], patterns: Iterable[str]) -> Optional[Path]:
        for candidate in iter_search_candidates(None, locations, patterns):
            return candidate
        return None

    if report_path is None and extra_dirs:
        report_path = _pick_from_locations(list(extra_dirs), [PRICE_MATCH_PATTERN])

    if report_path is None:
        report_path = _pick_from_locations([report_dir], [PRICE_MATCH_PATTERN, "*.xlsx"])

    if not report_path:
        warnings.append("未找到比价脚本输出文件，后续匹配数据将为空。")
        return pd.DataFrame(), None, warnings

    match_df = _safe_read_excel(report_path)
    if match_df.empty:
        warnings.append(f"比价文件 {report_path.name} 为空或读取失败。")
        return pd.DataFrame(), None, warnings

    try:
        store_suffixes = detect_store_suffixes(match_df.columns)
    except ValueError as exc:
        warnings.append(str(exc))
        return pd.DataFrame(), None, warnings

    missing_cols = validate_price_match_columns(match_df, store_suffixes)
    if missing_cols:
        warnings.append(f"比价结果缺少关键列: {missing_cols}")

    match_df = match_df.copy()
    match_df["match_sku_key"] = match_df.apply(lambda row: _generate_match_key(row, store_suffixes), axis=1)
    match_df["match_pair_id"] = match_df.apply(
        lambda row: _hash_pair(
            _sanitize_numeric(row.get(f"条码_{store_suffixes[0]}")),
            _sanitize_numeric(row.get(f"条码_{store_suffixes[1]}")),
        ),
        axis=1,
    )
    match_df["match_type"] = match_df.apply(
        lambda row: "barcode"
        if _sanitize_numeric(row.get(f"条码_{store_suffixes[0]}")) and _sanitize_numeric(row.get(f"条码_{store_suffixes[1]}"))
        else "fuzzy",
        axis=1,
    )

    logging.info("比价匹配结果加载完成：%s，行数 %d", report_path.name, len(match_df))
    return match_df, store_suffixes, warnings


def load_historical_sales(
    base_dir: Path,
    store_suffixes: Optional[Tuple[str, str]],
    preferred_file: Optional[Path] = None,
    extra_dirs: Optional[Iterable[Path]] = None,
) -> Tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    search_locations: list[Path] = []
    if extra_dirs:
        search_locations.extend(list(extra_dirs))
    search_locations.append(base_dir / "historical_sales")

    hist_path: Optional[Path] = None
    for candidate in iter_search_candidates(preferred_file, search_locations, PANEL_HISTORICAL_PATTERNS):
        hist_path = candidate
        break

    if not hist_path:
        warnings.append("未找到历史销售数据文件。")
        return pd.DataFrame(), warnings

    try:
        workbook = pd.read_excel(hist_path, sheet_name=None)
    except Exception as exc:
        warnings.append(f"读取历史销售文件失败：{exc}")
        return pd.DataFrame(), warnings

    sheets = list(workbook.keys())
    if not sheets:
        warnings.append(f"历史销售文件 {hist_path.name} 为空。")
        return pd.DataFrame(), warnings

    store_map = {}
    if store_suffixes:
        store_map = {"Sheet1": store_suffixes[0], "Sheet2": store_suffixes[1]}

    historical_frames = []
    for idx, (sheet_name, sheet_df) in enumerate(workbook.items(), start=1):
        sheet_df = sheet_df.copy()
        if sheet_df.empty:
            continue
        suffix = store_map.get(sheet_name) or (store_suffixes[idx - 1] if store_suffixes and idx <= len(store_suffixes) else f"Store{idx}")
        missing_cols = [col for col in HISTORICAL_REQUIRED_COLUMNS if col not in sheet_df.columns]
        if missing_cols:
            warnings.append(f"历史销售 {sheet_name} 缺少列 {missing_cols}")
        sheet_df["数据来源"] = suffix
        sheet_df["match_sku_key"] = sheet_df.apply(
            lambda row: _sanitize_numeric(row.get("条码"))
            or _sanitize_numeric(row.get("店内码"))
            or _hash_pair(str(row.get("商品名称", "")), str(row.get("规格", ""))),
            axis=1,
        )
        historical_frames.append(sheet_df)

    if not historical_frames:
        warnings.append(f"历史销售文件 {hist_path.name} 无有效数据。")
        return pd.DataFrame(), warnings

    historical_df = pd.concat(historical_frames, ignore_index=True)
    logging.info("历史销售数据加载完成：%s，行数 %d", hist_path.name, len(historical_df))
    return historical_df, warnings


def _extract_sheet(workbook: Dict[str, pd.DataFrame], index: int) -> pd.DataFrame:
    try:
        sheet_name = list(workbook.keys())[index]
        return workbook[sheet_name].copy()
    except IndexError:
        return pd.DataFrame()


def load_orders(
    base_dir: Path,
    preferred_file: Optional[Path] = None,
    extra_dirs: Optional[Iterable[Path]] = None,
    default_date: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    warnings: list[str] = []
    search_locations: list[Path] = []
    if extra_dirs:
        search_locations.extend(list(extra_dirs))
    search_locations.append(base_dir / "orders")

    orders_path: Optional[Path] = None
    for candidate in iter_search_candidates(preferred_file, search_locations, PANEL_ORDERS_PATTERNS):
        orders_path = candidate
        break

    if not orders_path:
        warnings.append("未找到门店订单聚合文件。")
        return pd.DataFrame(), pd.DataFrame(), warnings

    try:
        workbook = pd.read_excel(orders_path, sheet_name=None)
    except Exception as exc:
        warnings.append(f"读取订单文件失败：{exc}")
        return pd.DataFrame(), pd.DataFrame(), warnings

    if not workbook:
        warnings.append(f"订单文件 {orders_path.name} 为空。")
        return pd.DataFrame(), pd.DataFrame(), warnings

    store_orders = _normalize_columns(_extract_sheet(workbook, 0))
    store_traffic = _normalize_columns(_extract_sheet(workbook, 1))
    product_traffic = _normalize_columns(_extract_sheet(workbook, 2))
    cost_sheet = _normalize_columns(_extract_sheet(workbook, 3))

    if not store_traffic.empty and "统计日期" in store_traffic.columns and "日期" not in store_traffic.columns:
        store_traffic = store_traffic.rename(columns={"统计日期": "日期"})
    if not product_traffic.empty and "统计日期" in product_traffic.columns and "日期" not in product_traffic.columns:
        product_traffic = product_traffic.rename(columns={"统计日期": "日期"})
    if not cost_sheet.empty and "统计日期" in cost_sheet.columns and "日期" not in cost_sheet.columns:
        cost_sheet = cost_sheet.rename(columns={"统计日期": "日期"})

    if store_orders.empty:
        warnings.append("订单 Sheet1 为空，无法生成事实表。")
    else:
        missing = [col for col in ORDERS_REQUIRED_COLUMNS["store_orders"] if col not in store_orders.columns]
        if missing:
            warnings.append(f"订单 Sheet1 缺列 {missing}")

    orders_fact = pd.DataFrame()
    if not store_orders.empty:
        orders_fact = store_orders.rename(columns={"店内码": "店内码", "条码": "条码"}).copy()
        for time_col in ["下单时间", "日期"]:
            if time_col in orders_fact.columns:
                orders_fact[time_col] = pd.to_datetime(orders_fact[time_col], errors="coerce")
        if "下单时间" in orders_fact.columns:
            orders_fact["下单日期"] = orders_fact["下单时间"].dt.date
        orders_fact["match_sku_key"] = orders_fact.apply(
            lambda row: _sanitize_numeric(row.get("条码"))
            or _sanitize_numeric(row.get("店内码"))
            or _hash_pair(str(row.get("商品名称", "")), str(row.get("规格", ""))),
            axis=1,
        )

    traffic_dim_parts = []
    if not store_traffic.empty:
        miss = [col for col in ORDERS_REQUIRED_COLUMNS["store_traffic"] if col not in store_traffic.columns]
        if miss:
            warnings.append(f"订单 Sheet2 缺列 {miss}")
        store_traffic = store_traffic.copy()
        if "日期" in store_traffic.columns:
            store_traffic["日期"] = pd.to_datetime(store_traffic["日期"], errors="coerce")
        store_traffic["dataset"] = "store_traffic"
        traffic_dim_parts.append(store_traffic)

    if not product_traffic.empty:
        miss = [col for col in ORDERS_REQUIRED_COLUMNS["product_traffic"] if col not in product_traffic.columns]
        if miss:
            warnings.append(f"订单 Sheet3 缺列 {miss}")
        product_traffic = product_traffic.copy()
        if "日期" in product_traffic.columns:
            product_traffic["日期"] = pd.to_datetime(product_traffic["日期"], errors="coerce")
        product_traffic["match_sku_key"] = product_traffic.apply(
            lambda row: _sanitize_numeric(row.get("条码"))
            or _sanitize_numeric(row.get("店内码"))
            or _hash_pair(str(row.get("商品名称", "")), str(row.get("规格", ""))),
            axis=1,
        )
        product_traffic["dataset"] = "product_traffic"
        traffic_dim_parts.append(product_traffic)

    if not cost_sheet.empty:
        base_id_cols = [col for col in ("门店ID", "店铺ID", "门店编号", "店铺编号") if col in cost_sheet.columns]
        base_name_cols = [col for col in ("门店名称", "店铺名称") if col in cost_sheet.columns]
        meta_cols = base_id_cols + base_name_cols
        meta_cols += [col for col in ("开业时间", "加盟时间") if col in cost_sheet.columns]
        if "日期" not in cost_sheet.columns:
            if default_date:
                cost_sheet["日期"] = pd.to_datetime(default_date.date())
            else:
                cost_sheet["日期"] = pd.Timestamp.now().normalize()
        else:
            cost_sheet["日期"] = pd.to_datetime(cost_sheet["日期"], errors="coerce")

        meta_set = set(meta_cols + ["日期"])
        value_columns = [col for col in cost_sheet.columns if col not in meta_set]
        reshaped = cost_sheet
        id_vars = [col for col in (meta_cols + ["日期"]) if col in cost_sheet.columns]
        if value_columns:
            reshaped = cost_sheet.melt(id_vars=id_vars, value_vars=value_columns, var_name="成本项目", value_name="金额")
        if "商品名称" in reshaped.columns and "成本项目" in reshaped.columns:
            reshaped["商品名称"] = reshaped["商品名称"].fillna(reshaped["成本项目"])
        elif "商品名称" not in reshaped.columns and "成本项目" in reshaped.columns:
            reshaped["商品名称"] = reshaped["成本项目"]
        elif "商品名称" not in reshaped.columns:
            reshaped["商品名称"] = "门店成本"
        if "金额" not in reshaped.columns and value_columns:
            reshaped = reshaped.rename(columns={value_columns[0]: "金额"})
        reshaped["match_sku_key"] = reshaped.apply(
            lambda row: _hash_pair(str(row.get("门店ID") or row.get("店铺ID") or row.get("门店名称") or row.get("店铺名称")), str(row.get("商品名称", ""))),
            axis=1,
        )
        reshaped["dataset"] = "cost"
        traffic_dim_parts.append(reshaped)

    traffic_dim = pd.concat(traffic_dim_parts, ignore_index=True) if traffic_dim_parts else pd.DataFrame()
    if not orders_fact.empty:
        logging.info("订单事实表行数：%d", len(orders_fact))
    if not traffic_dim.empty:
        logging.info("流量/成本维度行数：%d", len(traffic_dim))

    return orders_fact, traffic_dim, warnings


def safe_write_table(df: pd.DataFrame, path: Path) -> Optional[Path]:
    if df is None or df.empty:
        return None
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception as exc:
        logging.warning("写入 %s 失败（%s），回退到 CSV。", path.name, exc)
        fallback = path.with_suffix(".csv")
        df.to_csv(fallback, index=False)
        return fallback


def _extract_display_name(suffix: str) -> str:
    if not suffix:
        return ""
    parts = str(suffix).split("-", 1)
    if len(parts) == 2 and parts[1].strip():
        return parts[1].strip()
    return str(suffix).strip()


def _series_to_key_set(series: pd.Series) -> set[str]:
    if series is None or series.empty:
        return set()
    return {str(value).strip() for value in series.dropna() if str(value).strip()}


def _compute_stockouts(match_df: pd.DataFrame, suffix: str) -> Dict[str, Optional[int]]:
    stock_col = f"库存_{suffix}"
    if stock_col not in match_df.columns:
        return {"zero_stock_matched": None, "zero_stock_with_sales": None, "has_stock_data": False}
    stock_series = pd.to_numeric(match_df[stock_col], errors="coerce")
    zero_mask = stock_series.fillna(0) <= 0
    zero_count = int(zero_mask.sum())
    sales_col = f"月售_{suffix}"
    zero_with_sales: Optional[int] = None
    if sales_col in match_df.columns:
        sales_series = pd.to_numeric(match_df[sales_col], errors="coerce").fillna(0)
        zero_with_sales = int((zero_mask & (sales_series > 0)).sum())
    return {
        "zero_stock_matched": zero_count,
        "zero_stock_with_sales": zero_with_sales if zero_with_sales is not None else 0 if zero_count else 0,
        "has_stock_data": True,
    }


def compute_price_panel_metrics(
    match_df: pd.DataFrame,
    historical_df: pd.DataFrame,
    store_suffixes: Optional[Tuple[str, str]],
) -> Dict[str, object]:
    generated_at = datetime.now().isoformat()
    warnings: List[str] = []

    if match_df is None or match_df.empty:
        warnings.append("匹配结果为空，跳过指标计算。")
        return {"generated_at": generated_at, "metrics": [], "stores": [], "warnings": warnings}

    hist_available = historical_df is not None and not historical_df.empty and "数据来源" in historical_df.columns
    if not hist_available:
        warnings.append("历史销售数据缺失，部分指标无法计算。")

    inferred_suffixes: List[str] = []
    if store_suffixes:
        inferred_suffixes.extend(list(store_suffixes))
    if not inferred_suffixes and hist_available:
        inferred_suffixes.extend([str(val).strip() for val in historical_df["数据来源"].dropna().unique().tolist()])
    inferred_suffixes = [suffix for suffix in inferred_suffixes if suffix]
    if len(inferred_suffixes) < 2:
        warnings.append("未能识别到两家店铺的列后缀，指标将使用默认占位名称。")
        inferred_suffixes.extend(["本店", "竞对"])

    suffix_list = list(dict.fromkeys(inferred_suffixes))[:2]
    if len(suffix_list) < 2:
        suffix_list += ["竞对"]
    suffix_list = suffix_list[:2]

    store_records: List[Dict[str, object]] = []
    matched_keys = _series_to_key_set(match_df.get("match_sku_key", pd.Series(dtype=object)))
    matched_count = len(matched_keys)

    for suffix in suffix_list:
        display_name = _extract_display_name(suffix)
        role = suffix.split("-", 1)[0] if "-" in suffix else suffix
        store_info: Dict[str, object] = {
            "suffix": suffix,
            "display_name": display_name or suffix,
            "role": role,
        }

        store_key_set: set[str] = set()
        if hist_available:
            store_subset = historical_df.loc[historical_df["数据来源"] == suffix, "match_sku_key"]
            store_key_set = _series_to_key_set(store_subset)
        store_total = len(store_key_set) if store_key_set else 0
        store_info["total_sku"] = store_total

        coverage: Optional[float] = None
        if store_total:
            coverage = matched_count / store_total * 100
        store_info["match_coverage"] = coverage

        unique_count: Optional[int] = None
        if store_total:
            unique_count = max(store_total - matched_count, 0)
        store_info["unique_sku"] = unique_count

        stockouts = _compute_stockouts(match_df, suffix)
        store_info.update(stockouts)

        store_records.append(store_info)

    if len(store_records) < 2:
        # 兜底补齐第二个店铺信息
        store_records.append({
            "suffix": "竞对",
            "display_name": "竞对",
            "role": "竞对",
            "total_sku": 0,
            "match_coverage": None,
            "unique_sku": None,
            "zero_stock_matched": None,
            "zero_stock_with_sales": None,
            "has_stock_data": False,
        })

    store_a, store_b = store_records[0], store_records[1]

    metrics: List[Dict[str, object]] = [
        {
            "id": "matched_pairs",
            "label": "匹配SKU数",
            "value": matched_count,
            "unit": "个",
            "context": {
                "stores": [store_a.get("display_name"), store_b.get("display_name")],
            },
        },
    ]

    def _add_rate_metric(store_info: Dict[str, object], identifier: str) -> None:
        coverage_val = store_info.get("match_coverage")
        metrics.append(
            {
                "id": identifier,
                "label": f"{store_info.get('display_name')}匹配覆盖率",
                "value": round(coverage_val, 1) if coverage_val is not None else None,
                "unit": "%",
                "context": {
                    "matched": matched_count,
                    "total": store_info.get("total_sku"),
                },
            }
        )

    _add_rate_metric(store_a, "match_rate_store_a")
    _add_rate_metric(store_b, "match_rate_store_b")

    def _add_unique_metric(store_info: Dict[str, object], identifier: str) -> None:
        metrics.append(
            {
                "id": identifier,
                "label": f"{store_info.get('display_name')}独有SKU",
                "value": store_info.get("unique_sku"),
                "unit": "个",
                "context": {
                    "total": store_info.get("total_sku"),
                    "matched": matched_count,
                },
            }
        )

    _add_unique_metric(store_a, "unique_store_a")
    _add_unique_metric(store_b, "unique_store_b")

    metrics.append(
        {
            "id": "stockout_alert",
            "label": "零库存SKU提醒",
            "value": store_a.get("zero_stock_matched"),
            "unit": "个",
            "context": {
                store_a.get("display_name"): {
                    "zero": store_a.get("zero_stock_matched"),
                    "with_sales": store_a.get("zero_stock_with_sales"),
                },
                store_b.get("display_name"): {
                    "zero": store_b.get("zero_stock_matched"),
                    "with_sales": store_b.get("zero_stock_with_sales"),
                },
                "difference": None
                if store_a.get("zero_stock_matched") is None or store_b.get("zero_stock_matched") is None
                else store_a.get("zero_stock_matched") - store_b.get("zero_stock_matched"),
            },
        }
    )

    return {
        "generated_at": generated_at,
        "matched_sku_count": matched_count,
        "stores": store_records,
        "metrics": metrics,
        "warnings": warnings,
    }


def write_price_panel_metrics(
    match_df: pd.DataFrame,
    historical_df: pd.DataFrame,
    store_suffixes: Optional[Tuple[str, str]],
    output_dir: Path,
) -> Tuple[Optional[Path], Dict[str, object]]:
    payload = compute_price_panel_metrics(match_df, historical_df, store_suffixes)
    target_path = output_dir / "price_panel_metrics.json"
    try:
        with open(target_path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        return target_path, payload
    except Exception as exc:
        logging.warning("写入指标文件 %s 失败：%s", target_path.name, exc)
        return None, payload


def write_run_log(result: ETLResult, base_dir: Path, run_date: datetime) -> Path:
    log_file = base_dir / f"etl_run_log_{run_date.strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w", encoding="utf-8") as fp:
        json.dump(result.to_dict(), fp, ensure_ascii=False, indent=2)
    return log_file


def _sanitize_filename(name: str) -> str:
    base = re.sub(r"[\\/:*?\"<>|]", "_", str(name).strip()) or "store"
    if not base.lower().endswith(".xlsx"):
        base = f"{base}.xlsx"
    return base


def _prepare_price_input_files(panel_data_dir: Path, raw_dir: Path) -> Optional[Tuple[Path, Path, str, str]]:
    search_locations: list[Path] = []
    if panel_data_dir and panel_data_dir.exists():
        search_locations.append(panel_data_dir)
    search_locations.append(raw_dir / "historical_sales")

    hist_path: Optional[Path] = None
    for candidate in iter_search_candidates(None, search_locations, PANEL_HISTORICAL_PATTERNS):
        hist_path = candidate
        break

    if not hist_path:
        logging.warning("自动比价：未找到历史销售数据文件，跳过比价脚本调用。")
        return None

    try:
        workbook = pd.read_excel(hist_path, sheet_name=None)
    except Exception as exc:
        logging.warning("自动比价：读取历史销售文件失败：%s", exc)
        return None

    if not workbook or len(workbook) < 2:
        logging.warning("自动比价：历史销售文件需至少包含本店与竞店两个工作表。")
        return None

    sheets = list(workbook.keys())
    store_sheet = next((name for name in sheets if "本店" in name), sheets[0])
    rival_sheet = next((name for name in sheets if any(k in name for k in ("竞", "对", "友商"))), sheets[1] if len(sheets) > 1 else None)

    if not rival_sheet:
        logging.warning("自动比价：历史销售文件未能识别竞店工作表，默认使用第二个工作表。")
        if len(sheets) > 1:
            rival_sheet = sheets[1]
        else:
            return None

    store_df = workbook.get(store_sheet, pd.DataFrame())
    rival_df = workbook.get(rival_sheet, pd.DataFrame())

    if store_df.empty or rival_df.empty:
        logging.warning("自动比价：本店或竞店数据为空，跳过比价脚本调用。")
        return None

    store_file = raw_dir / "price_match" / _sanitize_filename(store_sheet)
    rival_file = raw_dir / "price_match" / _sanitize_filename(rival_sheet)
    try:
        store_df.to_excel(store_file, index=False)
        rival_df.to_excel(rival_file, index=False)
    except Exception as exc:
        logging.warning("自动比价：写入临时比价输入文件失败：%s", exc)
        return None

    return store_file, rival_file, store_sheet.strip(), rival_sheet.strip()


def run_price_comparison(panel_data_dir: Path, raw_dir: Path) -> Optional[Path]:
    prepared = _prepare_price_input_files(panel_data_dir, raw_dir)
    if not prepared:
        return None

    store_file, rival_file, store_name, rival_name = prepared

    script_path = BASE_DIR / "product_comparison_tool_local.py"
    if not script_path.exists():
        logging.warning("自动比价：未找到比价脚本 %s", script_path)
        return None

    env = os.environ.copy()
    env.update(
        {
            "COMPARE_STORE_A_FILE": str(store_file),
            "COMPARE_STORE_B_FILE": str(rival_file),
            "COMPARE_STORE_A_NAME": store_name,
            "COMPARE_STORE_B_NAME": rival_name,
        }
    )

    before_files = set(REPORT_DIR.glob(PRICE_MATCH_PATTERN))
    try:
        subprocess.run([sys.executable, str(script_path)], cwd=BASE_DIR, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        logging.warning("自动比价：比价脚本执行失败：%s", exc)
        return None

    after_files = set(REPORT_DIR.glob(PRICE_MATCH_PATTERN))
    new_files = after_files - before_files
    if new_files:
        latest_path = max(new_files, key=lambda p: p.stat().st_mtime)
    else:
        latest_path = find_latest_file(REPORT_DIR, PRICE_MATCH_PATTERN)

    if latest_path:
        logging.info("自动比价：生成比价结果 %s", latest_path.name)
    else:
        logging.warning("自动比价：比价脚本未生成结果文件。")

    return latest_path


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比价测算面板 ETL")
    parser.add_argument("--date", type=str, help="业务日期(YYYY-MM-DD)，用于记录日志", default=None)
    parser.add_argument("--dry-run", action="store_true", help="仅加载数据与校验，不生成中间层文件")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--match-file", type=str, help="指定比价匹配结果 Excel 的完整路径", default=None)
    parser.add_argument("--historical-file", type=str, help="指定历史销售聚合 Excel 的完整路径", default=None)
    parser.add_argument("--orders-file", type=str, help="指定订单聚合 Excel（含四个 Sheet）的完整路径", default=None)
    parser.add_argument(
        "--auto-match",
        action="store_true",
        help="在加载比价结果前自动调用比价脚本生成最新匹配数据",
    )
    parser.add_argument(
        "--panel-data-dir",
        type=str,
        help="门店数据-比价看板模块目录（用于自动搜索历史销售/订单数据）",
        default=None,
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    run_date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    logging.info("=== 比价测算面板 ETL 开始，业务日期 %s ===", run_date.date())

    result = ETLResult(warnings=[])

    panel_data_dir = Path(args.panel_data_dir).expanduser().resolve() if args.panel_data_dir else PANEL_DATA_DIR
    panel_extra_dirs: list[Path] = []
    if panel_data_dir.exists():
        panel_extra_dirs.append(panel_data_dir)
    else:
        logging.debug("默认面板数据目录不存在，跳过：%s", panel_data_dir)

    match_file = Path(args.match_file).expanduser().resolve() if args.match_file else None
    historical_file = Path(args.historical_file).expanduser().resolve() if args.historical_file else None
    orders_file = Path(args.orders_file).expanduser().resolve() if args.orders_file else None

    if args.auto_match and match_file is None:
        auto_match_result = run_price_comparison(panel_data_dir, RAW_DIR)
        if auto_match_result:
            match_file = auto_match_result
        else:
            logging.warning("自动比价未生成结果文件，将继续按既有逻辑查找比价输出。")

    match_df, store_suffixes, warnings = load_price_match(REPORT_DIR, preferred_file=match_file, extra_dirs=panel_extra_dirs)
    result.warnings.extend(warnings)
    result.match_pairs_rows = len(match_df)

    historical_df, hist_warnings = load_historical_sales(
        RAW_DIR,
        store_suffixes,
        preferred_file=historical_file,
        extra_dirs=panel_extra_dirs,
    )
    result.warnings.extend(hist_warnings)
    result.historical_rows = len(historical_df)

    orders_fact, traffic_dim, order_warnings = load_orders(
        RAW_DIR,
        preferred_file=orders_file,
        extra_dirs=panel_extra_dirs,
        default_date=run_date,
    )
    result.warnings.extend(order_warnings)
    result.orders_rows = len(orders_fact)
    result.traffic_rows = len(traffic_dim)

    if args.dry_run:
        logging.info("Dry-run 模式：跳过写入中间层文件。")
    else:
        written_paths = []
        if not match_df.empty:
            written = safe_write_table(match_df, INTERMEDIATE_DIR / "matched_pairs.parquet")
            if written:
                written_paths.append(written)
        if not orders_fact.empty:
            written = safe_write_table(orders_fact, INTERMEDIATE_DIR / "orders_fact.parquet")
            if written:
                written_paths.append(written)
        if not traffic_dim.empty:
            written = safe_write_table(traffic_dim, INTERMEDIATE_DIR / "traffic_cost_dim.parquet")
            if written:
                written_paths.append(written)
        if not historical_df.empty:
            written = safe_write_table(historical_df, INTERMEDIATE_DIR / "historical_sales.parquet")
            if written:
                written_paths.append(written)
        metrics_path, metrics_payload = write_price_panel_metrics(match_df, historical_df, store_suffixes, INTERMEDIATE_DIR)
        if metrics_path:
            written_paths.append(metrics_path)
        for warning in metrics_payload.get("warnings", []):
            if warning not in result.warnings:
                result.warnings.append(warning)
        for path in written_paths:
            logging.info("写入文件：%s", path)

    log_path = write_run_log(result, LOG_DIR, run_date)
    logging.info("运行日志写入：%s", log_path.name)

    if result.warnings:
        logging.warning("本次运行产生警告：%s", result.warnings)
    logging.info("=== 比价测算面板 ETL 结束 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
