import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.db import engine

st.set_page_config(page_title="CareerOps", layout="wide")
st.title("CareerOps")

with engine.connect() as conn:
    df = pd.read_sql(
        text("""
            SELECT company_name, title, status, last_change_at, canonical_id
              FROM applications
             ORDER BY last_change_at DESC
        """),
        conn,
    )

st.subheader(f"Applications: {len(df)}")
counts = df["status"].value_counts()
cols = st.columns(max(len(counts), 1))
for col, (status, n) in zip(cols, counts.items()):
    col.metric(status, int(n))

st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Ranked queue")

with engine.connect() as conn:
    queue = pd.read_sql(
        text("""
        SELECT j.fit_score, j.company_name, j.title, j.location_raw,
               c.sponsorship_status, j.posted_at, j.apply_url,
               (SELECT count(*) FROM applications a
                 WHERE regexp_replace(lower(a.company_name), '[^a-z0-9]', '', 'g')
                     = regexp_replace(lower(j.company_name), '[^a-z0-9]', '', 'g')
               ) AS applied_here
          FROM jobs j
              LEFT JOIN companies c
                     ON c.source = j.source AND c.board_token = j.board_token
             WHERE j.is_eligible
               AND j.closed_at IS NULL
               AND j.fit_score IS NOT NULL
               AND NOT EXISTS (
                     SELECT 1 FROM applications a
                      WHERE a.canonical_id = j.canonical_id)
             ORDER BY j.fit_score DESC
             LIMIT 50
        """),
        conn,
    )

st.caption(f"Top {len(queue)} eligible, open, unapplied jobs by fit score")
st.dataframe(
    queue,
    use_container_width=True,
    hide_index=True,
    column_config={"apply_url": st.column_config.LinkColumn("apply")},
)