import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time

# Configuración de página
st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7", page_icon="https://www.miaa.mx/favicon.ico")

# --- CSS DEFINITIVO PARA CENTRADO Y ALINEACIÓN ---
st.markdown("""
    <style>
    /* Ocultar elementos de Streamlit */
    #MainMenu, header {visibility: hidden;}
    .block-container {padding-top: 0.5rem !important; padding-bottom: 0rem !important;}
    
    /* Contenedor que agrupa logo y título y los centra */
    .full-header {
        display: flex;
        justify-content: center; /* Centra horizontalmente todo el bloque */
        align-items: center;     /* Centra verticalmente el logo con el título */
        gap: 20px;               /* Espacio entre logo y título */
        margin-bottom: 20px;
    }
    
    /* Título azul exacto */
    .custom-title {
        color: #00E5FF !important; 
        font-size: 3.5rem;
        font-weight: bold;
        text-shadow: none !important;
        margin: 0;
    }
    </style>
""", unsafe_allow_html=True)

# --- CABECERA (LOGO A LA IZQUIERDA DEL TÍTULO, TODO CENTRADO) ---
st.markdown('<div class="full-header">', unsafe_allow_html=True)
st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=150)
st.markdown('<h1 class="custom-title">Sistema de Monitoreo MIAA 24/7</h1>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# --- LÓGICA ---
@st.cache_resource
def get_engines():
    return create_engine(st.secrets["databases"]["url_dic"]), create_engine(st.secrets["databases"]["url_scada"])

ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

# --- PROCESAMIENTO ---
# (Mantenemos tu lógica intacta)
df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
query_inc = "SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'"
df_inc = pd.read_sql(query_inc, ENGINE_SCADA)
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

lista_apg = []
for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
    inc = mapa_inc.get(pozo_key, "Sin incidencia")
    val_nivel = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
    
    if row['VALUE'] == 0:
        lista_apg.append({
            "Pozo": info['Pozos'],
            "Estatus_Paro": inc,
            "Fecha": row['FECHA'].date(),
            "Hora": row['FECHA'].time()
        })

# --- VISUALIZACIÓN ---
if lista_apg:
    df_f = pd.DataFrame(lista_apg).sort_values(by='Fecha', ascending=False)
    st.dataframe(df_f, use_container_width=True, hide_index=True, height=750)
else:
    st.info("No hay pozos apagados.")
