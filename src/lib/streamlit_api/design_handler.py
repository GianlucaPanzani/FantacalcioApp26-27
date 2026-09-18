import base64
import mimetypes
from pathlib import Path
import pandas as pd
import streamlit as st

from lib.utils import columns_to_user_view_dict, interest_colors_dict


def highlight_interest(interest) -> str:
    """Return the configured table-cell style for an interest level."""
    color = interest_colors_dict.get(interest)
    return f"background-color: {color}; color: #000000" if color else ""


def get_color_per_role(role: str, color_version=True, rgba=False) -> str:
    """Return the configured display color for a Fantacalcio role."""
    role_colors = {
        "P": "#EACD6D" if color_version else "orange",
        "D": "#8FCD92" if color_version else "green",
        "C": "#73B3E7" if color_version else "blue",
        "A": "#DE7D7D" if color_version else "red",
    }
    role_colors_rgba = {
        "P": "rgba(240,165,0,0.80)",
        "D": "rgba(88,185,92,0.80)",
        "C": "rgba(33,150,243,0.80)",
        "A": "rgba(230,70,60,0.80)",
    }
    if rgba:
        return role_colors_rgba.get(role, "")
    return role_colors.get(str(role).strip().upper(), "")


def highlight_player_role(row: pd.Series) -> list[str]:
    """Apply the Fantacalcio role color to every cell in a player row."""
    role_color = get_color_per_role(row.get("R", row.get("fanta_role", "")))
    if not role_color:
        return [""] * len(row)
    return [f"background-color: {role_color}; color: #212121"] * len(row)


def get_circular_role_icon(
    role: str, font_size=14, height=24, width=24, y_translation=-2,
):
    """Return an HTML circular badge for a Fantacalcio role."""
    return f"""
    <span style="
        width: {width}px;
        height: {height}px;
        border-radius: 50%;
        background-color: {get_color_per_role(role, color_version=False)};
        display: inline-flex;
        align-items: center;
        justify-content: center;
        vertical-align: middle;
        transform: translateY({y_translation}px);
        line-height: 1;
        margin: 0;
        font-weight: bold;
        color: white;
        font-size: {font_size}px;
    ">{role}</span>
    """


def get_icon(icon_name: str) -> str:
    """Return a Markdown data URL for a bundled navigation icon."""
    icon_path = Path(f"icons/icons8-{icon_name}-94.png")
    encoded_icon = base64.b64encode(icon_path.read_bytes()).decode("ascii")
    return f"![AI](data:image/png;base64,{encoded_icon})"


def get_emoji(page_name: str) -> str:
    """Return the navigation emoji or Material icon configured for a page."""
    page_icons = {
        "login": "⚽",
        "registration": "👤",
        "auction": ":material/gavel:",
        "fantacalcio": "⚽",
        "statistics": "📊",
        "selection": "🏃‍♂️",
        "settings": "⚙️",
    }
    return page_icons[page_name]


def get_background_img_path(page: str) -> str:
    """Return the conventional background-image path for a page."""
    return f"img/background/{page}.jpeg"


def get_user_view_of_column(column: str) -> str:
    """Return the readable label configured for an internal column name."""
    return columns_to_user_view_dict.get(
        column,
        column.replace("_", " ").capitalize(),
    )


def get_col_from_user_view(user_view: str) -> str:
    """Return the internal column name matching a readable label."""
    for column, label in columns_to_user_view_dict.items():
        if user_view == label:
            return column
    return user_view


def config_page(page_title="Fantacalcio tool", page_icon="⚽", layout="wide", initial_sidebar_state="expanded"):
    """Configure the page title, icon, layout and initial sidebar state."""
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )

def bottom_caption():
    """Display the application copyright caption at the bottom of the page."""
    st.space(100)
    with st.bottom:
        st.caption("© 2026 GP · All rights reserved")
    return


def set_page_background(image_path: str | Path):
    """Set a local image as the fixed application background.

    Params
    ----------
    image_path : str or pathlib.Path
        Local image to encode and embed in the page.

    Returns
    -------
    object
        Streamlit element containing the generated background styles.
    """
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Background image not found: {image_path}")

    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")

    return st.html(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image:
                linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)),
                url("data:{mime_type};base64,{encoded_image}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}
        </style>
        """
    )


def set_dark_background():
    """Apply the shared dark background style to keyed card containers."""
    return st.html(
        f"""
        <style>
        [class*="st-key-dark-card-"] {{
            background-color: rgba(14, 17, 23, 0.94);
            border-radius: 0.75rem;
            padding: 1rem;
        }}
        </style>
        """
    )


def set_player_card_background():
    """Apply the bundled image background to player portrait cards."""
    image_path = Path(__file__).resolve().parents[2] / "img/background/player_card_bg.png"
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")

    return st.html(
        f"""
        <style>
        [class*="st-key-dark-card-player-portrait-"] {{
            background-image:
                linear-gradient(to bottom, rgba(14, 17, 23, 0.10), rgba(14, 17, 23, 0.80)),
                url("data:image/png;base64,{encoded_image}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        }}
        </style>
        """
    )


def set_text_size(text_size, class_name):
    """Set metric-label text size for elements matching a CSS class fragment."""
    return st.html(
        f"""
        <style>
        [class*="{class_name}"] [data-testid="stMetricLabel"] p {{
            font-size: {str(text_size)}rem;
        }}
        </style>
        """
    )

def sidebar_navigation_size(font_size=1.15, font_weight=600):
    """Set the font size and weight of sidebar navigation links."""
    return st.html(
        f"""
        <style>
        [data-testid="stSidebarNavLink"] span {{
            font-size: {font_size}rem;
            font-weight: {font_weight};
        }}
        </style>
        """
    )

def thick_divider(height=4, border="none", background_color="#808080", border_radius=4, margin=20):
    """Display a divider with configurable size, color, border and spacing."""
    return st.html(
        f"""
        <hr style="
            height: {str(height)}px;
            border: {str(border)};
            background-color: {str(background_color)};
            border-radius: {border_radius}px;
            margin: {str(margin)}px 0;
        ">
        """
    )

def toast_css_format(background_color="#47BEF1", border_color="#FFFFFF", border_size=2):
    """Apply background and border styles to Streamlit toast messages."""
    return st.html(
        f"""
        <style>
        [data-testid="stToast"] {{
            background-color: {background_color};
            border: {border_size}px solid {border_color};
            box-shadow: 0 4px 14px rgba(255, 179, 0, 0.35);
        }}

        [data-testid="stToast"] * {{
            color: #664D03 !important;
        }}
        </style>
        """
    )
