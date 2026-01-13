import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


st.set_page_config(page_title="Advance Perubatan", layout="wide")

# =========================
# PATHS
# =========================
BASE_DIR = Path(__file__).parent
CSV_DIR = BASE_DIR / "csv_export"

CSV_FILES = {
    "Jadual Advance Perubatan": CSV_DIR / "Jadual_Advance_Perubatan_Update.csv",
    "Beri Advance Detail": CSV_DIR / "Beri_Advance_Detail.csv",
    "Bayar Balik Advance Detail": CSV_DIR / "Bayar_Balik_Advance_Detail.csv",
}


# =========================
# HELPERS
# =========================
def file_mtime(path: Path):
    if not path.exists():
        return None
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=ZoneInfo("UTC"))
    return ts.astimezone(ZoneInfo("Asia/Kuala_Lumpur"))


def clean_common(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = pd.Index([str(c).strip() for c in df.columns])

    cols = df.columns.astype(str)
    bad = cols.str.lower().isin(["nan", "none", ""])
    unnamed = cols.str.match(r"(?i)^unnamed")
    df = df.loc[:, ~(bad | unnamed)]

    df = df.replace("None", pd.NA)
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    return df

def format_currency_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    keyword_matches = ["amount", "amaun"]
    explicit_amount_cols = {"total adv", "total potongan", "baki"}

    for col in df.columns:
        col_lower = str(col).strip().lower()
        if any(k in col_lower for k in keyword_matches) or col_lower in explicit_amount_cols:
            s = pd.to_numeric(df[col], errors="coerce")
            df[col] = s.apply(lambda x: f"RM {x:,.2f}" if pd.notna(x) else "RM 0.00")
    return df

@st.cache_data(ttl=5, show_spinner=False)
def load_csv_normal(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = clean_common(df)
    df.reset_index(drop=True, inplace=True)
    return df

@st.cache_data(ttl=5, show_spinner=False)
def load_csv_jadual(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, encoding="utf-8-sig", header=None)
    raw = raw.dropna(axis=1, how="all")

    header_row = None
    for i in range(min(15, len(raw))):
        row = raw.iloc[i].astype(str).str.lower()
        if row.str.contains("bil").any():
            header_row = i
            break

    if header_row is None:
        head = raw.head(min(15, len(raw))).astype(str)
        scores = head.apply(
            lambda r: (r.str.strip().replace({"nan": "", "None": "", "none": ""}) != "").sum(),
            axis=1,
        )
        header_row = int(scores.idxmax())

    df = raw.iloc[header_row + 1:].copy()
    df.columns = raw.iloc[header_row]

    df = clean_common(df)
    df.reset_index(drop=True, inplace=True)
    return df

def reorder_columns(df: pd.DataFrame, desired_order: list[str]) -> pd.DataFrame:
    existing = [c for c in desired_order if c in df.columns]
    remaining = [c for c in df.columns if c not in existing]
    return df[existing + remaining]

def append_total_row(df: pd.DataFrame, label_col: str | None = None) -> pd.DataFrame:
    df_total = df.copy()
    total_row = {}

    for col in df_total.columns:
        if df_total[col].astype(str).str.startswith("RM").any():
            nums = (
                df_total[col].astype(str)
                .str.replace("RM", "", regex=False)
                .str.replace(",", "", regex=False)
            )
            nums = pd.to_numeric(nums, errors="coerce").fillna(0)
            total_row[col] = f"RM {nums.sum():,.2f}"
        else:
            total_row[col] = ""

    if label_col and label_col in df_total.columns:
        total_row[label_col] = "TOTAL"

    return pd.concat([df_total, pd.DataFrame([total_row])], ignore_index=True)

def normalize_id_staf(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    s = s.dropna().astype(int).astype(str)
    return s

# =========================
# HEADER UI
# =========================
st.title("Jadual Advance Perubatan")

last_updated = max(
    [t for t in (file_mtime(p) for p in CSV_FILES.values()) if t],
    default=None
)

if last_updated:
    st.caption(f"🕒 Last updated: {last_updated.strftime('%d %b %Y, %I:%M:%S %p')}")
else:
    st.warning("Last updated time not available (file not found).")

st.divider()

# =========================
# GLOBAL SIDEBAR SLICER (Name shown, filter by ID Staf)
# =========================
@st.cache_data(ttl=30, show_spinner=False)
def build_name_to_ids() -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}

    # Jadual: ID Staf + Nama Staf
    p = CSV_FILES["Jadual Advance Perubatan"]
    if p.exists():
        dfj = load_csv_jadual(p)
        if "ID Staf" in dfj.columns and "Nama Staf" in dfj.columns:
            ids = pd.to_numeric(dfj["ID Staf"], errors="coerce")
            names = dfj["Nama Staf"].astype(str).str.strip()
            temp = pd.DataFrame({"id": ids, "name": names})
            temp = temp.dropna(subset=["id"])
            temp["id"] = temp["id"].astype(int).astype(str)
            temp = temp[temp["name"].notna() & (temp["name"] != "") & (temp["name"].str.lower() != "none")]
            for _, r in temp.iterrows():
                mapping.setdefault(r["name"], set()).add(r["id"])

    # Beri: ID Staf + Full Name
    p = CSV_FILES["Beri Advance Detail"]
    if p.exists():
        dfb = load_csv_normal(p)
        if "ID Staf" in dfb.columns and "Full Name" in dfb.columns:
            ids = pd.to_numeric(dfb["ID Staf"], errors="coerce")
            names = dfb["Full Name"].astype(str).str.strip()
            temp = pd.DataFrame({"id": ids, "name": names})
            temp = temp.dropna(subset=["id"])
            temp["id"] = temp["id"].astype(int).astype(str)
            temp = temp[temp["name"].notna() & (temp["name"] != "") & (temp["name"].str.lower() != "none")]
            for _, r in temp.iterrows():
                mapping.setdefault(r["name"], set()).add(r["id"])

    # Bayar: ID Staf + Full Name
    p = CSV_FILES["Bayar Balik Advance Detail"]
    if p.exists():
        dfbb = load_csv_normal(p)
        if "ID Staf" in dfbb.columns and "Full Name" in dfbb.columns:
            ids = pd.to_numeric(dfbb["ID Staf"], errors="coerce")
            names = dfbb["Full Name"].astype(str).str.strip()
            temp = pd.DataFrame({"id": ids, "name": names})
            temp = temp.dropna(subset=["id"])
            temp["id"] = temp["id"].astype(int).astype(str)
            temp = temp[temp["name"].notna() & (temp["name"] != "") & (temp["name"].str.lower() != "none")]
            for _, r in temp.iterrows():
                mapping.setdefault(r["name"], set()).add(r["id"])

    return mapping

name_to_ids = build_name_to_ids()

with st.sidebar:
    st.subheader("Filter")

    selected_name = st.selectbox(
        "Nama Staf",
        options=["All"] + sorted(name_to_ids.keys()),
        key="slicer_nama_staf"
    )

    hide_zero_baki = st.toggle(
        "Hide zero baki (Jadual only)",
        value=False,
        help="Remove rows where Baki = RM 0.00 (only affects Jadual Advance Perubatan)"
    )

selected_ids: set[str] = set()
if selected_name != "All":
    selected_ids = name_to_ids.get(selected_name, set())



# =========================
# TABS
# =========================
tabs = st.tabs(list(CSV_FILES.keys()))

for tab, (label, csv_path) in zip(tabs, CSV_FILES.items()):
    with tab:
        if label != "Jadual Advance Perubatan":
            st.subheader(label)

        if not csv_path.exists():
            st.error(f"CSV not found: {csv_path}")
            continue

        # LOAD
        if label == "Jadual Advance Perubatan":
            df = load_csv_jadual(csv_path)
            label_col = "Nama Staf"
        else:
            df = load_csv_normal(csv_path)
            label_col = "Full Name"

        # FILTER by ID Staf (use for slicer only)
        if selected_ids and "ID Staf" in df.columns:
            ids = pd.to_numeric(df["ID Staf"], errors="coerce")
            df = df.loc[ids.notna()].copy()
            df["ID Staf"] = ids.loc[ids.notna()].astype(int).astype(str)
            df = df[df["ID Staf"].isin(selected_ids)]

        # FORMAT currency (after filter)
        df = format_currency_columns(df)

        # OPTIONAL: Hide zero baki (Jadual only) - MUST be before TOTAL row
        if label == "Jadual Advance Perubatan" and hide_zero_baki and "Baki" in df.columns:
            baki_num = (
                df["Baki"].astype(str)
                .str.replace("RM", "", regex=False)
                .str.replace(",", "", regex=False)
            )
            baki_num = pd.to_numeric(baki_num, errors="coerce").fillna(0)
            df = df[baki_num != 0]

        # Drop columns not shown (keep ID only for filtering above)
        df = df.drop(columns=["Bil.", "Text"], errors="ignore")
        df = df.drop(columns=["ID Staf"], errors="ignore")

        # TABLE SPECIFIC ORDER
        if label == "Beri Advance Detail":
            df = reorder_columns(df, [
                "Full Name",
                "Document Number",
                "Funds Center",
                "Document Type",
                "Posting Date",
                "Year/month",
                "Amount in local currency",
            ])

        elif label == "Bayar Balik Advance Detail":
            df = reorder_columns(df, [
                "Full Name",
                "No Rujukan",
                "PTJ",
                "Type",
                "Year/Month",
                "Amaun (RM)",
            ])

        elif label == "Jadual Advance Perubatan":
            df = reorder_columns(df, [
                "Nama Staf",
                "Total ADV",
                "Total Potongan",
                "Baki",
            ])

        # ADD TOTAL ROW (reflects filtered result)
        df = append_total_row(df, label_col=label_col)

        # index start from 1
        df = df.reset_index(drop=True)
        df.index = df.index + 1

        st.dataframe(df, use_container_width=True, height=520)

