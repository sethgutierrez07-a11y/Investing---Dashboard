"""
Entry point for Streamlit Community Cloud (Main file path stays `app.py`).

It only lists the pages, which is how they get professional names in the sidebar.
The home page itself is dashboard.py.
"""

import streamlit as st

pages = [
    st.Page("dashboard.py", title="Investing Dashboard", icon="📊", url_path="Investing_Dashboard", default=True),
    st.Page("pages/1_Daily_Brief.py", title="Daily Brief", icon="🗞️", url_path="Daily_Brief"),
    st.Page("pages/2_Holdings.py", title="Holdings", icon="💼", url_path="Holdings"),
    st.Page("pages/3_Strategy_Lab.py", title="Strategy Lab", icon="🧪", url_path="Strategy_Lab"),
    st.Page("pages/4_Dividends.py", title="Dividends", icon="💰", url_path="Dividends"),
]

st.navigation(pages).run()
