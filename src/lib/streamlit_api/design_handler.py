import base64
import mimetypes
from pathlib import Path
import streamlit as st



def config_page(page_title="Fantacalcio tool", page_icon="⚽", layout="wide", initial_sidebar_state="expanded"):
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )

def bottom_caption():
    st.space(100)
    with st.bottom:
        st.caption("© 2026 GP · All rights reserved")
    return


def set_page_background(image_path: str | Path):
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
    return st.html(
        """
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
    image_path = Path(__file__).resolve().parents[1] / "img/player_card_bg.png"
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
