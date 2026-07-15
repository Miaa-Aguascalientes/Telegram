import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time

# Configuración de página
st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7", page_icon="https://www.miaa.mx/favicon.ico")

# --- CSS DEFINITIVO ---
st.markdown("""
    <style>
    #MainMenu, header {visibility: hidden;}
    .block-container {padding-top: 0.5rem !important; padding-bottom: 0rem !important;}
    .custom-title {
        color: #00E5FF; 
        font-size: 3.5rem;
        font-weight: bold;
        text-shadow: 0px 0px 8px #00E5FF;
        margin-top: -10px;
    }
    .logo-container {margin-top: -10px;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXIÓN ---
@st.cache_resource
def get_engines():
    try:
        return create_engine(st.secrets["databases"]["url_dic"]), create_engine(st.secrets["databases"]["url_scada"])
    except: return None, None

ENGINE_DIC, ENGINE_SCADA = get_engines()

# --- PROCESAMIENTO ---
lista_apg = []

if ENGINE_DIC and ENGINE_SCADA:
    try:
        df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
        df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
        df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
        mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))

        tags = "', '".join(df_dic['bomba'].tolist())
        query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID) ORDER BY h.FECHA DESC"
        df = pd.read_sql(query, ENGINE_SCADA)

        cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
        tags_aux = [str(t) for col in cols_aux for t in df_dic[col].dropna().unique()]
        query_aux = f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
        df_h = pd.read_sql(query_aux, ENGINE_SCADA)
        mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

        for _, row in df.iterrows():
            info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
            pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
            inc = mapa_inc.get(pozo_key, "Sin incidencia")
            
            val_n = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
            
            if row['VALUE'] == 0:
                estatus = f"⚠️ {inc}" if inc != "Sin incidencia" else "❌ Desconocida"
                lista_apg.append({
                    "Estatus": estatus, "Pozo": info['Pozos'], "Fecha": row['FECHA'],
                    "Incidencia": inc, "Nivel": f"{val_n:.2f}" if val_n > 0 else ""
                })
    except Exception as e:
        st.error(f"Error técnico: {e}")

# --- CABECERA ---
col1, col2 = st.columns([1, 10])
with col1:
    st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=150)
with col2:
    st.markdown('<h1 class="custom-title">Sistema de Monitoreo MIAA 24/7</h1>', unsafe_allow_html=True)

# --- VISUALIZACIÓN ---
if lista_apg:
    df_f = pd.DataFrame(lista_apg).sort_values(by='Fecha', ascending=False)
    df_f['Hora'] = df_f['Fecha'].dt.strftime('%H:%M:%S')
    df_f['Fecha'] = df_f['Fecha'].dt.strftime('%d/%m/%y')
    
    def color_row(row):
        color = '#FFD700' if '⚠️' in row['Estatus'] else ('#FF0000' if '❌' in row['Estatus'] else 'inherit')
        return [f'color: {color}'] * len(row)

    st.dataframe(df_f.style.apply(color_row, axis=1), use_container_width=True, hide_index=True, height=750)
else:
    st.warning("No hay datos de pozos apagados en este momento.")
