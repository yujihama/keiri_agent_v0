from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from core.blocks.registry import BlockRegistry
from ui.tabs import design as tab_design
from ui.tabs import execute as tab_execute
from ui.tabs import logs as tab_logs
from ui.tabs import reviewer as tab_reviewer
from ui import logging as ulog


load_dotenv()


def main():
    st.set_page_config(page_title="Keiri Agent", layout="wide")
    st.title("Keiri Agent")

    registry = BlockRegistry()
    registry.load_specs()
    ulog.configure_logging()

    tab1, tab2, tab3, tab4 = st.tabs(["業務設計", "業務実施", "レビュー", "ログ"])
    with tab1:
        tab_design.render(registry)
    with tab2:
        tab_execute.render(registry)
    with tab3:
        tab_reviewer.render(registry)
    with tab4:
        tab_logs.render()


if __name__ == "__main__":
    main()


