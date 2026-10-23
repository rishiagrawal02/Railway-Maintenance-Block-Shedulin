"""Streamlit prototype application for Railway Maintenance Block Planning."""

import streamlit as st

import rbp.api as api


def main() -> None:
    st.set_page_config(page_title="Railway Maintenance Scheduler", layout="wide")
    st.title("Railway Maintenance Block Planning")
    st.caption(f"System Version: {api.get_version()}")


if __name__ == "__main__":
    main()
