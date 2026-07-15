import streamlit as st
import os
from dotenv import load_dotenv

load_dotenv(override=True)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

def init_auth():
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False

def render_auth_ui():
    init_auth()
    st.markdown(
        """
        <style>
        .stAppDeployButton {display: none !important;}
        .stDeployButton {display: none !important;}
        #MainMenu {visibility: hidden;}
        button[data-testid="stHeaderDropdownMenu"] {visibility: hidden;}
        footer {visibility: hidden;}
        div[data-testid="stConnectionStatus"] {display: none !important;}
        </style>
        """,
        unsafe_allow_html=True
    )
    with st.sidebar:
        st.write("---")
        if st.session_state.is_admin:
            st.success("Admin Mode Active")
            if st.button("Logout"):
                st.session_state.is_admin = False
                st.rerun()
            
            st.write("---")
            DB_PATH = os.getenv("DB_PATH", "data/inventory.db")
            if os.path.exists(DB_PATH):
                with open(DB_PATH, "rb") as f:
                    st.download_button(
                        label="Export Database",
                        data=f,
                        file_name="inventory_backup.db",
                        mime="application/octet-stream"
                    )
        else:
            with st.expander("Admin Login", expanded=False):
                pwd = st.text_input("Password", type="password")
                if st.button("Login"):
                    if pwd == ADMIN_PASSWORD:
                        st.session_state.is_admin = True
                        st.success("Logged in!")
                        st.rerun()
                    else:
                        st.error("Invalid password.")
        
        st.write("---")
        if st.button("Stop Server", help="Terminate the Streamlit server process."):
            st.warning("Server shutting down...")
            os._exit(0)

def is_admin():
    return st.session_state.get("is_admin", False)
