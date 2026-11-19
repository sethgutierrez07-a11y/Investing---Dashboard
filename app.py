"""
Entry point for Streamlit Community Cloud (Main file path stays `app.py`).

It only lists the pages, which is how they get professional names. The page menu runs along the top
of the app, so it is always visible and the sidebar stays free for the password and watchlist.
The home page itself is dashboard.py.
"""

import streamlit as st

pages = [
    st.Page("dashboard.py", title="Investing Dashboard", icon="📊", url_path="Investing_Dashboard", default=True),
    st.Page("pages/1_Daily_Brief.py", title="Daily Brief", icon="🗞️", url_path="Daily_Brief"),
    st.Page("pages/2_Holdings.py", title="Holdings", icon="💼", url_path="Holdings"),
    st.Page("pages/3_Strategy_Lab.py", title="Strategy Lab", icon="🧪", url_path="Strategy_Lab"),
    st.Page("pages/4_Dividends.py", title="Dividends", icon="💰", url_path="Dividends"),
    st.Page("pages/5_Risk.py", title="Risk", icon="🛡️", url_path="Risk"),
    st.Page("pages/6_Market.py", title="Market", icon="🌐", url_path="Market"),
    st.Page("pages/8_Deep_Dive.py", title="Stock Deep-Dive", icon="🔬", url_path="Deep_Dive"),
    st.Page("pages/7_Learn.py", title="Learn", icon="🎓", url_path="Learn"),
]

st.navigation(pages, position="top").run()
