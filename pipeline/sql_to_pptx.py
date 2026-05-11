"""
SQL Server -> Excel -> PowerPoint weekly MA%/CT report pipeline.
Run directly or via run_pipeline.bat (Windows Task Scheduler).
All config loaded from config.env in the same directory.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import pyodbc
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / "config.env")

LOG_FILE = SCRIPT_DIR / "pipeline.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SQL_SERVER    = os.getenv("SQL_SERVER",    "localhost")
SQL_DATABASE  = os.getenv("SQL_DATABASE",  "YourDatabase")
SQL_USERNAME  = os.getenv("SQL_USERNAME",  "")
SQL_PASSWORD  = os.getenv("SQL_PASSWORD",  "")
SQL_DRIVER    = os.getenv("SQL_DRIVER",    "ODBC Driver 17 for SQL Server")
SQL_QUERY     = os.getenv("SQL_QUERY",     "SELECT TOP 50 * FROM dbo.YourTable")
CT_QUERY      = os.getenv("CT_QUERY",      "")   # empty = reserve CT section as placeholder

OUTPUT_DIR    = Path(os.getenv("OUTPUT_DIR", str(SCRIPT_DIR / "output")))
PPT_MAX_ROWS  = int(os.getenv("PPT_MAX_ROWS", "25"))

SLIDE_TITLE   = os.getenv("SLIDE_TITLE",   "Weekly MA% & Cycle Time Report")
KEY_TAKEAWAY  = os.getenv("KEY_TAKEAWAY",  "")   # optional full-width banner below title
MA_LABEL      = os.getenv("MA_LABEL",      "Machine Availability % (MA%)")
CT_LABEL      = os.getenv("CT_LABEL",      "Cycle Time (CT)")
TOOL_COLUMN   = os.getenv("TOOL_COLUMN",   "Tool")
TARGET_COLUMN = os.getenv("TARGET_COLUMN", "Target")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

C_NAV       = RGBColor(0x1F, 0x4E, 0x79)   # dark navy
C_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
C_SLIDE_BG  = RGBColor(0xF5, 0xF8, 0xFF)
C_SUBTITLE  = RGBColor(0x60, 0x60, 0x60)
C_FOOTER    = RGBColor(0x99, 0x99, 0x99)
C_MA_BANNER = RGBColor(0x1F, 0x4E, 0x79)   # navy
C_CT_BANNER = RGBColor(0xED, 0x7D, 0x31)   # orange
C_TAKEAWAY  = RGBColor(0x2E, 0x74, 0xB5)   # medium blue
C_ROW_ALT   = RGBColor(0xE9, 0xF1, 0xF7)
C_ROW_BASE  = RGBColor(0xFF, 0xFF, 0xFF)
C_TGT_BG    = RGBColor(0xD9, 0xE1, 0xF2)   # soft blue for Target column
C_TOOL_BG   = RGBColor(0xF2, 0xF2, 0xF2)   # light grey for Tool column
C_GREEN     = RGBColor(0x00, 0xB0, 0x50)   # at/above target
C_YELLOW    = RGBColor(0xFF, 0xC0, 0x00)   # below target up to -2 pp
C_RED       = RGBColor(0xFF, 0x00, 0x00)   # below target by >2 pp
C_BLACK     = RGBColor(0x00, 0x00, 0x00)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ma_color(value, target) -> RGBColor:
    """Green / yellow / red based on (value - target) in percentage points."""
    try:
        v, t = float(value), float(target)
        if v >= t:
            return C_GREEN
        if v >= t - 0.02:
            return C_YELLOW
        return C_RED
    except (TypeError, ValueError):
        return C_ROW_BASE


def _fmt_pct(value, decimals: int = 1) -> str:
    """Convert a decimal (e.g. 0.9512) to a percentage string (e.g. '95.1%')."""
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "" if value is None else str(value)


def _ppt_cell(cell, text: str, bg: RGBColor, fg: RGBColor,
              bold: bool = False, font_size: float = 9,
              align: PP_ALIGN = PP_ALIGN.CENTER) -> None:
    cell.fill.solid()
    cell.fill.fore_color.rgb = bg
    tf = cell.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.runs[0] if p.runs else p.add_run()
    run.text           = text
    run.font.color.rgb = fg
    run.font.bold      = bold
    run.font.size      = Pt(font_size)
    run.font.name      = "Calibri"


def _banner(slide, text: str, left, top, width, height,
            bg: RGBColor, fg: RGBColor, font_size: float = 10) -> None:
    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE, left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg
    shape.line.fill.background()
    tf = shape.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text           = text
    run.font.color.rgb = fg
    run.font.bold      = True
    run.font.size      = Pt(font_size)
    run.font.name      = "Calibri"


def _col_order(df: pd.DataFrame, include_tool: bool = True) -> list:
    """Return column list in display order: [Tool,] Target, WW…"""
    cols    = list(df.columns)
    ww_cols = [c for c in cols if c not in (TOOL_COLUMN, TARGET_COLUMN)]
    ordered = []
    if include_tool and TOOL_COLUMN in cols:
        ordered.append(TOOL_COLUMN)
    if TARGET_COLUMN in cols:
        ordered.append(TARGET_COLUMN)
    ordered.extend(ww_cols)
    return ordered

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

def _conn_str() -> str:
    base = f"DRIVER={{{SQL_DRIVER}}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};"
    if SQL_USERNAME and SQL_PASSWORD:
        return base + f"UID={SQL_USERNAME};PWD={SQL_PASSWORD};"
    return base + "Trusted_Connection=yes;"


def _run_query(sql: str) -> pd.DataFrame:
    conn = pyodbc.connect(_conn_str(), timeout=30)
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()


def fetch_data():
    log.info("Connecting to %s / %s", SQL_SERVER, SQL_DATABASE)
    df_ma = _run_query(SQL_QUERY)
    log.info("MA%%  fetched: %d rows x %d cols", len(df_ma), len(df_ma.columns))
    df_ct = None
    if CT_QUERY.strip():
        df_ct = _run_query(CT_QUERY)
        log.info("CT    fetched: %d rows x %d cols", len(df_ct), len(df_ct.columns))
    return df_ma, df_ct

# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

_THIN   = Side(style="thin", color="CCCCCC")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _write_excel_sheet(ws, df: pd.DataFrame, is_ma: bool) -> None:
    hdr_color = "1F4E79" if is_ma else "ED7D31"
    hdr_fill  = PatternFill("solid", fgColor=hdr_color)
    hdr_font  = Font(color="FFFFFF", bold=True, size=11, name="Calibri")

    cols = list(df.columns)

    # Header row
    for ci, col_name in enumerate(cols, start=1):
        c = ws.cell(row=1, column=ci, value=col_name)
        c.fill      = hdr_fill
        c.font      = hdr_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border    = _BORDER
    ws.row_dimensions[1].height = 20

    # Data rows
    for ri, rec in enumerate(df.to_dict("records"), start=2):
        alt      = (ri % 2) == 0
        alt_hex  = "E9F1F7" if alt else "FFFFFF"
        tgt_val  = rec.get(TARGET_COLUMN)

        for ci, col_name in enumerate(cols, start=1):
            value = rec[col_name]
            c     = ws.cell(row=ri, column=ci)
            is_ww = col_name not in (TOOL_COLUMN, TARGET_COLUMN)

            if is_ma and is_ww and tgt_val is not None:
                try:
                    v, t            = float(value), float(tgt_val)
                    c.value         = v
                    c.number_format = "0.0%"
                    if v >= t:
                        c.fill = PatternFill("solid", fgColor="00B050")
                    elif v >= t - 0.02:
                        c.fill = PatternFill("solid", fgColor="FFC000")
                    else:
                        c.fill = PatternFill("solid", fgColor="FF0000")
                    c.font = Font(bold=True, size=10, name="Calibri", color="000000")
                except (TypeError, ValueError):
                    c.value = value
                    c.fill  = PatternFill("solid", fgColor=alt_hex)
                    c.font  = Font(size=10, name="Calibri")
            elif is_ma and col_name == TARGET_COLUMN:
                try:
                    c.value         = float(value)
                    c.number_format = "0.00%"
                except (TypeError, ValueError):
                    c.value = value
                c.fill = PatternFill("solid", fgColor="D9E1F2")
                c.font = Font(size=10, name="Calibri")
            else:
                c.value = "" if value is None else value
                c.fill  = PatternFill("solid", fgColor=alt_hex)
                c.font  = Font(size=10, name="Calibri")

            c.alignment = Alignment(
                horizontal="left" if col_name == TOOL_COLUMN else "center",
                vertical="center"
            )
            c.border = _BORDER

    # Auto-size columns
    for col in ws.columns:
        width = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 3, 40)

    ws.freeze_panes     = "B2"
    ws.auto_filter.ref  = ws.dimensions


def export_to_excel(df_ma: pd.DataFrame, df_ct, path: Path) -> None:
    wb       = Workbook()
    ws_ma    = wb.active
    ws_ma.title = "MA%"
    _write_excel_sheet(ws_ma, df_ma, is_ma=True)

    if df_ct is not None:
        ws_ct = wb.create_sheet("CT")
        _write_excel_sheet(ws_ct, df_ct, is_ma=False)

    wb.save(path)
    log.info("Excel saved: %s", path)

# ---------------------------------------------------------------------------
# PowerPoint layout constants (all values in EMU via Inches())
# ---------------------------------------------------------------------------

_SL_W = Inches(13.33)
_SL_H = Inches(7.50)
_ML   = Inches(0.30)           # left/right margin
_AW   = _SL_W - 2 * _ML       # available width  (~12.73")
_GAP  = Inches(0.22)           # gap between MA and CT tables
_MA_W = int(_AW * 0.565)       # MA table width (~7.19" — wider: has Tool column)
_CT_W = _AW - _MA_W - _GAP    # CT table width (~5.32" — narrower: no Tool column)
_CT_L = _ML + _MA_W + _GAP    # CT table left edge

_T_TITLE  = Inches(0.15)
_H_TITLE  = Inches(0.55)
_T_SUB    = Inches(0.70)
_H_SUB    = Inches(0.28)
_T_DIV    = Inches(0.98)
_H_DIV    = Inches(0.04)
_H_TAKE   = Inches(0.38)       # key takeaway banner height
_H_BANNER = Inches(0.30)       # section banner height
_H_FOOTER = Inches(0.22)

# ---------------------------------------------------------------------------
# PowerPoint builder
# ---------------------------------------------------------------------------

def build_pptx(df_ma: pd.DataFrame, df_ct, path: Path, excel_filename: str) -> None:
    prs              = Presentation()
    prs.slide_width  = _SL_W
    prs.slide_height = _SL_H
    slide            = prs.slides.add_slide(prs.slide_layouts[6])   # blank

    # Slide background
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = C_SLIDE_BG

    # ── Title ─────────────────────────────────────────────────────────────
    tb   = slide.shapes.add_textbox(_ML, _T_TITLE, _AW, _H_TITLE)
    run  = tb.text_frame.paragraphs[0].add_run()
    run.text           = SLIDE_TITLE
    run.font.size      = Pt(22)
    run.font.bold      = True
    run.font.color.rgb = C_NAV
    run.font.name      = "Calibri"

    # ── Subtitle ──────────────────────────────────────────────────────────
    sb   = slide.shapes.add_textbox(_ML, _T_SUB, _AW, _H_SUB)
    srun = sb.text_frame.paragraphs[0].add_run()
    srun.text           = (
        f"Source: SQL Server  •  Database: {SQL_DATABASE}  •  "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    srun.font.size      = Pt(8.5)
    srun.font.color.rgb = C_SUBTITLE
    srun.font.name      = "Calibri"

    # ── Divider ───────────────────────────────────────────────────────────
    div = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE, _ML, _T_DIV, _AW, _H_DIV
    )
    div.fill.solid()
    div.fill.fore_color.rgb = C_NAV
    div.line.fill.background()

    # ── Key takeaway banner (optional full-width) ──────────────────────────
    has_take = bool(KEY_TAKEAWAY.strip())
    banner_t = _T_DIV + _H_DIV + Inches(0.06)
    if has_take:
        _banner(slide, KEY_TAKEAWAY, _ML, banner_t, _AW, _H_TAKE,
                C_TAKEAWAY, C_WHITE, font_size=11)
        banner_t += _H_TAKE + Inches(0.06)

    # ── Section banners ───────────────────────────────────────────────────
    _banner(slide, MA_LABEL, _ML,   banner_t, _MA_W, _H_BANNER, C_MA_BANNER, C_WHITE, 9)
    _banner(slide, CT_LABEL, _CT_L, banner_t, _CT_W, _H_BANNER, C_CT_BANNER, C_WHITE, 9)

    # ── Table geometry ────────────────────────────────────────────────────
    tbl_top = banner_t + _H_BANNER + Inches(0.02)
    tbl_h   = int(_SL_H - _H_FOOTER - Inches(0.05)) - tbl_top
    n_data  = min(len(df_ma), PPT_MAX_ROWS)

    # ── MA% table ─────────────────────────────────────────────────────────
    display_ma = df_ma.head(n_data)
    ordered_ma = _col_order(display_ma, include_tool=True)
    n_ma_cols  = len(ordered_ma)

    ma_tbl = slide.shapes.add_table(
        n_data + 1, n_ma_cols, _ML, tbl_top, _MA_W, tbl_h
    ).table

    # Tool column gets 28% of MA table width; remaining columns split equally
    has_tool = TOOL_COLUMN in ordered_ma
    tool_w   = int(_MA_W * 0.28) if has_tool else 0
    data_w   = int((_MA_W - tool_w) / (n_ma_cols - (1 if has_tool else 0)))
    for i, col in enumerate(ordered_ma):
        ma_tbl.columns[i].width = tool_w if col == TOOL_COLUMN else data_w

    # Header row
    for ci, col_name in enumerate(ordered_ma):
        _ppt_cell(ma_tbl.cell(0, ci), col_name,
                  bg=C_NAV, fg=C_WHITE, bold=True, font_size=9)

    # Data rows
    for ri, rec in enumerate(display_ma[ordered_ma].to_dict("records"), start=1):
        tgt = rec.get(TARGET_COLUMN)
        alt = C_ROW_ALT if ri % 2 == 0 else C_ROW_BASE

        for ci, col_name in enumerate(ordered_ma):
            val   = rec[col_name]
            is_ww = col_name not in (TOOL_COLUMN, TARGET_COLUMN)

            if col_name == TOOL_COLUMN:
                _ppt_cell(ma_tbl.cell(ri, ci),
                          str(val) if val is not None else "",
                          bg=C_TOOL_BG, fg=C_BLACK, font_size=8.5,
                          align=PP_ALIGN.LEFT)
            elif col_name == TARGET_COLUMN:
                _ppt_cell(ma_tbl.cell(ri, ci),
                          _fmt_pct(val, decimals=2),
                          bg=C_TGT_BG, fg=C_BLACK, font_size=8.5)
            elif is_ww:
                _ppt_cell(ma_tbl.cell(ri, ci),
                          _fmt_pct(val, decimals=1),
                          bg=_ma_color(val, tgt), fg=C_BLACK,
                          bold=True, font_size=8.5)

    # ── CT table (or placeholder) ─────────────────────────────────────────
    if df_ct is not None and len(df_ct) > 0:
        display_ct = df_ct.head(n_data)
        # CT table omits the Tool column — rows align visually with MA by position
        ordered_ct = _col_order(display_ct, include_tool=False)
        n_ct_cols  = len(ordered_ct)

        ct_tbl = slide.shapes.add_table(
            n_data + 1, n_ct_cols, _CT_L, tbl_top, _CT_W, tbl_h
        ).table

        ct_col_w = int(_CT_W / n_ct_cols)
        for i in range(n_ct_cols):
            ct_tbl.columns[i].width = ct_col_w

        # Header — orange to match CT section banner
        for ci, col_name in enumerate(ordered_ct):
            _ppt_cell(ct_tbl.cell(0, ci), col_name,
                      bg=C_CT_BANNER, fg=C_WHITE, bold=True, font_size=9)

        # Data rows — show raw CT numbers, no colour coding
        for ri, rec in enumerate(display_ct[ordered_ct].to_dict("records"), start=1):
            alt = C_ROW_ALT if ri % 2 == 0 else C_ROW_BASE
            for ci, col_name in enumerate(ordered_ct):
                val = rec[col_name]
                try:
                    display_v = f"{float(val):.2f}" if val is not None else ""
                except (TypeError, ValueError):
                    display_v = str(val) if val is not None else ""
                _ppt_cell(ct_tbl.cell(ri, ci), display_v,
                          bg=alt, fg=C_BLACK, font_size=8.5)
    else:
        # Placeholder when CT_QUERY is not configured
        ph   = slide.shapes.add_textbox(
            _CT_L + Inches(0.15), tbl_top + Inches(0.25),
            _CT_W - Inches(0.2), Inches(0.5)
        )
        prun = ph.text_frame.paragraphs[0].add_run()
        prun.text           = "Set CT_QUERY in config.env to populate this section."
        prun.font.size      = Pt(8.5)
        prun.font.italic    = True
        prun.font.color.rgb = C_SUBTITLE
        prun.font.name      = "Calibri"

    # ── Footer ────────────────────────────────────────────────────────────
    ft_top = int(_SL_H - _H_FOOTER - Inches(0.03))
    ft     = slide.shapes.add_textbox(_ML, ft_top, _AW, _H_FOOTER)
    frun   = ft.text_frame.paragraphs[0].add_run()
    frun.text = (
        f"Showing {n_data} of {len(df_ma)} rows  —  Full data: {excel_filename}"
        if len(df_ma) > PPT_MAX_ROWS else
        f"Full data: {excel_filename}"
    )
    frun.font.size      = Pt(7.5)
    frun.font.color.rgb = C_FOOTER
    frun.font.name      = "Calibri"

    prs.save(path)
    log.info("PowerPoint saved: %s", path)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    log.info("=" * 60)
    log.info("Pipeline started")

    df_ma, df_ct = fetch_data()

    excel_path = OUTPUT_DIR / f"report_{stamp}.xlsx"
    export_to_excel(df_ma, df_ct, excel_path)

    pptx_path = OUTPUT_DIR / f"report_{stamp}.pptx"
    build_pptx(df_ma, df_ct, pptx_path, excel_path.name)

    log.info(
        "Pipeline complete.  Excel: %s  |  PPTX: %s",
        excel_path.name, pptx_path.name
    )
    log.info("=" * 60)


if __name__ == "__main__":
    run()
