import streamlit as st
import dropbox
import pandas as pd
import json
import os
import random


dbx = dropbox.Dropbox(st.secrets["DROPBOX_TOKEN"])
REMOTE_CSV_PATH = st.secrets["DROPBOX_PATH"]  # e.g. "/gpt_matches.csv"


def upload_to_dropbox(local_file="gpt_matches.csv"):
    """Upload local CSV to Dropbox at REMOTE_CSV_PATH."""
    try:
        with open(local_file, "rb") as f:
            dbx.files_upload(
                f.read(),
                REMOTE_CSV_PATH,
                mode=dropbox.files.WriteMode("overwrite")
            )
    except Exception as e:
        st.warning(f"Could not upload CSV to Dropbox: {e}")


def download_from_dropbox(local_file="gpt_matches.csv"):
    """Download CSV from Dropbox to local file. Returns True if successful."""
    try:
        md, res = dbx.files_download(REMOTE_CSV_PATH)
    except dropbox.exceptions.ApiError:
        # Probably file not found yet -> treat as first run
        return False
    except Exception as e:
        # Any other bad input / token / etc.
        st.warning(f"Could not download CSV from Dropbox: {e}")
        return False

    with open(local_file, "wb") as f:
        f.write(res.content)
    return True



if download_from_dropbox():
    st.info("Loaded latest CSV from Dropbox.")
else:
    st.warning("No Dropbox CSV found — using local file.")
# -----------------------------------------------------------------------------
# 0. Page config
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Database Name Annotation",
    layout="wide",
)

# -----------------------------------------------------------------------------
# 1. Paths / constants
# -----------------------------------------------------------------------------
SAMPLE_JSON_PATH = "sample_200.json"
CSV_PATH = "gpt_matches.csv"   # ID, GPT, and per-user columns


# -----------------------------------------------------------------------------
# 2. Data loading / saving helpers
# -----------------------------------------------------------------------------
@st.cache_data
def load_samples():
    """
    Load the 200 sampled entries from JSON.
    Expected format: list of dicts with keys: id, title, abstract
    """
    with open(SAMPLE_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["id"] = df["id"].astype(str)
    return df


def load_annotations():
    """
    Load annotations and force a clean structure:
    - exactly one row per ID from sample_200.json
    - drop any duplicate IDs from the CSV
    """
    samples_df = load_samples()
    ids = samples_df["id"].astype(str).tolist()

    if os.path.exists(CSV_PATH):
        ann_df = pd.read_csv(CSV_PATH, dtype={"ID": str})
    else:
        # Initialize fresh CSV if it doesn't exist
        ann_df = pd.DataFrame({
            "ID": ids,
            "GPT": [0] * len(ids),
        })

    # Ensure ID is string
    ann_df["ID"] = ann_df["ID"].astype(str)

    # 🔧 1) Drop duplicate IDs (keep first)
    ann_df = ann_df.drop_duplicates(subset=["ID"], keep="first")

    # 🔧 2) Keep only IDs that are really in sample_200.json
    ann_df = ann_df[ann_df["ID"].isin(ids)]

    # 🔧 3) Make sure we have *exactly* one row per ID in sample_200.json
    base = pd.DataFrame({"ID": ids})  # ordered like sample_200.json
    ann_df = base.merge(ann_df, on="ID", how="left")

    # 🔧 4) Ensure GPT exists and is int
    if "GPT" not in ann_df.columns:
        ann_df["GPT"] = 0
    ann_df["GPT"] = ann_df["GPT"].fillna(0).astype(int)

    return ann_df


def save_annotations(df: pd.DataFrame):
    """
    Save annotations back to CSV, again enforcing:
    - one row per ID
    - no duplicates
    """
    df = df.copy()
    df["ID"] = df["ID"].astype(str)
    df = df.drop_duplicates(subset=["ID"], keep="first")
    df.to_csv(CSV_PATH, index=False)



# -----------------------------------------------------------------------------
# 3. Sidebar: User login
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("Login")

    default_username = st.session_state.get("username", "")
    username = st.text_input(
        "Username",
        value=default_username,
        placeholder="Enter your username",
    )

    if not username.strip():
        st.warning("Please enter your username to start annotating.")
        st.stop()

    username = username.strip()
    st.session_state["username"] = username

st.title("Manual Annotation of Database Names in PubMed Abstracts")

st.markdown("""### Annotation Instructions

You are reviewing literature to **identify database / study / cohort names** used in research on  
**Mental Health and Aggression in Children and Adolescents**.  
For each title and abstract, decide **in one step** whether the paper is relevant and whether it clearly mentions a database/study/cohort.""")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        **Include papers that involve:**  
        - Environmental or social data  
        - Hormonal data  
        - Brain imaging  
        - Mental-health or aggression phenotypes  
        - Genetics data  
        """
    )

with col2:
    st.markdown(
        """
        **Discard papers that are:**  
        - Not focused on mental health  
        - Adults-only  
        - Not based on individual-level data  
        - Tumor-related  
        - Animal studies  
        """
    )

st.markdown(
    """
---

### Your Task

After reading the title and abstract:

- **Yes** → The paper fits the topic **and** mentions a database/study/cohort (named or unnamed).  
- **No** → The paper does *not* fit the topic **or** it fits but does *not* mention any database/study/cohort.

Use the **Yes/No** buttons below each abstract.  
Each user must label all **200 entries**.
"""
)


# -----------------------------------------------------------------------------
# 4. Load data & ensure user column exists
# -----------------------------------------------------------------------------
samples_df = load_samples()
ann_df = load_annotations()

# Add user column if not existing
if username not in ann_df.columns:
    ann_df[username] = pd.NA
    save_annotations(ann_df)
    ann_df = load_annotations()

# -----------------------------------------------------------------------------
# 5. Progress and remaining IDs for this user
# -----------------------------------------------------------------------------
user_col = ann_df[username]

total_entries = len(ann_df)
already_labeled = user_col.notna().sum()
remaining = total_entries - already_labeled

st.subheader(f"User: {username}")
st.write(f"Labeled entries: **{already_labeled} / {total_entries}**")

progress_fraction = already_labeled / total_entries if total_entries > 0 else 0
st.progress(progress_fraction)

if remaining == 0:
    st.success("🎉 You have labeled all 200 entries. Thank you!")
    st.stop()

# IDs not yet labeled by this user
remaining_ids = ann_df.loc[user_col.isna(), "ID"].tolist()

# -----------------------------------------------------------------------------
# 6. Choose a random ID for this session
# -----------------------------------------------------------------------------
if "current_id" not in st.session_state or st.session_state["current_id"] not in remaining_ids:
    st.session_state["current_id"] = random.choice(remaining_ids)

current_id = st.session_state["current_id"]

# Get title + abstract for this ID
row = samples_df[samples_df["id"] == current_id]
if row.empty:
    st.error(f"No entry found in sample_200.json for ID {current_id}.")
    st.stop()

row = row.iloc[0]
title = row["title"]
abstract = row["abstract"]

# -----------------------------------------------------------------------------
# 7. Show the current abstract and buttons
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(f"### Current ID: `{current_id}`")
st.markdown(f"**Title:** {title}")
st.markdown("**Abstract:**")
st.write(abstract)

st.markdown("---")
st.markdown(
    """
**Question (placeholder):**  
Does this title/abstract clearly describe or refer to a *database / cohort / registry*  
that is relevant for our systematic database search?
"""
)

col_yes, col_no = st.columns(2)

yes_clicked = col_yes.button("✅ Yes – contains a relevant database")
no_clicked = col_no.button("❌ No – does *not* contain a relevant database")

# -----------------------------------------------------------------------------
# 8. Handle clicks: update CSV, pick next ID, avoid overwriting
# -----------------------------------------------------------------------------
def update_label_and_rerun(label_value: int):
    """
    label_value: 1 for Yes, 0 for No
    """
    global ann_df
    # Reload to avoid stale cache when multiple users work in parallel (simple safeguard)
    ann_df_local = load_annotations()
    if username not in ann_df_local.columns:
        ann_df_local[username] = pd.NA

    mask = (ann_df_local["ID"] == current_id)
    if mask.sum() == 0:
        st.error(f"Internal error: ID {current_id} not found in annotation file.")
        return

    # Only set value if it was NaN before -> avoid overwriting existing labels
    current_val = ann_df_local.loc[mask, username].iloc[0]
    if pd.isna(current_val):
        ann_df_local.loc[mask, username] = label_value
        save_annotations(ann_df_local)
        upload_to_dropbox("gpt_matches.csv")
        
    # else: do nothing, preserves previous decision

    # Force picking a new ID on next run
    st.session_state["current_id"] = None
    st.rerun()   # <- use this instead of st.experimental_rerun()


if yes_clicked:
    update_label_and_rerun(1)

if no_clicked:
    update_label_and_rerun(0)

# If neither clicked, just show current state (no-op on reload)
