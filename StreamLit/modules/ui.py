import streamlit as st


def render_footer() -> None:
    """Render a standard footer across pages with licensing and ownership.

    - StreamLit/ app is PolyForm Noncommercial 1.0.0 (noncommercial use only)
    - Other parts of the repo are MIT
    - Copyright held by KC Explorer LLC
    """
    st.markdown("---")
    st.caption(
        "© 2025 KC Explorer LLC — MyChartExplorer is licensed for noncommercial use under "
        "PolyForm Noncommercial 1.0.0. "
        "For commercial use, contact kc@mychartexplorer.com."
    )