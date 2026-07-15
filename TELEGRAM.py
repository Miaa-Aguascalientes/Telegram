import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time

st.set_page_config(
    layout="wide", 
    page_title="Sistema MIAA 24/7", 
    page_icon="https://www.miaa.mx/favicon.ico"
)

# --- CSS PARA ESTILO Y POSICIÓN ---
st.markdown("""
    <style>
    /* Ocultar elementos de Streamlit */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Subir todo el contenido al máximo */
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0rem;
    }
    
    /* Estilo del título azul neón */
    .custom-title {
        color: #00FFFF;
        font-size: 3rem;
        font-weight: bold;
        text-shadow: 0px 0px 10px #00FFFF;
        margin-top: -20px;
    }
    
    .logo-container {
        margin-top: -20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- CABECERA ---
col1, col2 = st.columns([1, 10])
with col1:
    st.markdown('<div class="logo-container">', unsafe_allow_html=True)
    st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=100)
    st.markdown('</div>', unsafe_allow_html=True)
with col2:
    # Usamos markdown para aplicar nuestra clase de título personalizada
    st.markdown('<h1 class="custom-title">Sistema de Monitoreo MIAA 24/7</h1>', unsafe_allow_html=True)

# --- RESTO DE TU LÓGICA (PROCESAMIENTO Y VISUALIZACIÓN) ---
# ... (Aquí iría tu código de base de datos y la creación de lista_apg) ...

# Asegúrate de usar esta configuración en tu tabla para mantener la limpieza:
if lista_apg:
    df_final = pd.DataFrame(lista_apg)
    # ... (tu ordenamiento) ...
    
    # Renderizado final sin índice
    st.dataframe(
        df_final.style.apply(color_text, axis=1), 
        use_container_width=True, 
        hide_index=True,
        height=700 
    )
