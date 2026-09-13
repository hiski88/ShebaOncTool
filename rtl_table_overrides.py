"""RTL presentation helpers for read-only Streamlit dataframes.

Streamlit's dataframe renderer is visually left-to-right even when the surrounding
app is RTL. For Hebrew screens we therefore reverse displayed dataframe columns
and move the horizontal scroller to the far right after rendering. The underlying
DataFrame is not mutated.
"""
from __future__ import annotations

import streamlit.components.v1 as components


def _rtl_dataframe_value(value):
    """Return a presentation copy whose first logical column renders on the right."""
    try:
        import pandas as pd
    except Exception:
        return value
    if isinstance(value, pd.DataFrame):
        return value.loc[:, list(reversed(value.columns))]
    return value


def _scroll_last_dataframe_right() -> None:
    components.html(
        """
        <script>
        (() => {
          const host = window.parent;
          if (!host) return;
          const move = () => {
            const frames = host.document.querySelectorAll('[data-testid="stDataFrame"]');
            const frame = frames[frames.length - 1];
            if (!frame) return;
            let scroller = null;
            let largest = 0;
            const nodes = [frame, ...frame.querySelectorAll('*')];
            for (const node of nodes) {
              const overflow = Number(node.scrollWidth || 0) - Number(node.clientWidth || 0);
              if (overflow > largest + 4) {
                largest = overflow;
                scroller = node;
              }
            }
            if (!scroller || largest <= 4) return;
            scroller.scrollLeft = scroller.scrollWidth;
            if (typeof scroller.scrollTo === 'function') {
              scroller.scrollTo({left: scroller.scrollWidth, top: scroller.scrollTop, behavior: 'auto'});
            }
          };
          [0, 80, 200, 450, 900].forEach((delay) => host.setTimeout(move, delay));
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )


def install(app_module) -> None:
    st = app_module.st
    if getattr(st, "_medstaff_rtl_dataframe_installed", False):
        return

    original_dataframe = st.dataframe

    def rtl_dataframe(data=None, *args, **kwargs):
        shown = _rtl_dataframe_value(data)
        if "column_order" in kwargs and kwargs["column_order"] is not None:
            kwargs["column_order"] = list(reversed(list(kwargs["column_order"])))
        result = original_dataframe(shown, *args, **kwargs)
        _scroll_last_dataframe_right()
        return result

    st.dataframe = rtl_dataframe
    st._medstaff_rtl_dataframe_installed = True
