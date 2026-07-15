import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time

st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7", page_icon="https://www.miaa.mx/favicon.ico")

# --- CSS INTEGRADO ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 0.5rem !important; padding-bottom: 0rem;}
    .custom-title {color: #00FFFF; font-size: 3rem; font-weight: bold; text-shadow: 0px 0px 10px #00FFFF; margin-top: -20px;}
    .logo-container {margin-top: -20px;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXIÓN ---
@st.cache_resource
def get_engines():
    try:
        return create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True), create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True)
    except:
        return None, None

ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

# --- CABECERA ---
col1, col2 = st.columns([1, 10])
with col1:
    st.markdown('<div class="logo-container">', unsafe_allow_html=True)
    st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=100)
    st.markdown('</div>', unsafe_allow_html=True)
with col2:
    st.markdown('<h1 class="custom-title">Sistema de Monitoreo MIAA 24/7</h1>', unsafe_allow_html=True)

# --- PROCESAMIENTO ---
lista_apg = [] # <-- INICIALIZACIÓN CRÍTICA PARA QUE NO FALLA EL IF
if ENGINE_DIC and ENGINE_SCADA:
    try:
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

        for _, row in df.iterrows():
            info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
            pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
            inc = mapa_inc.get(pozo_key, "Sin incidencia")
            
            val_nivel = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
            val_n_arr = float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0)
            val_n_par = float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)
            
            if row['VALUE'] == 0:
                estatus = f"⚠️ {inc}" if inc != "Sin incidencia" else ("✅ Normal" if (val_n_arr > 0 and val_n_par > 0 and (val_nivel >= val_n_arr or (val_n_par > val_nivel > val_n_arr))) else "❌ Desconocida")
                lista_apg.append({
                    "Estatus_Paro": estatus, "Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(),
                    "TS": row['FECHA'], "Incidencia": inc, "H_paro": convertir_a_hora(mapa_aux.get(str(info['H_paro']))),
                    "H_arranque": convertir_a_hora(mapa_aux.get(str(info['H_arranque']))), "Nivel": f"{val_nivel:.2f}" if val_nivel > 0 else "",
                    "Niv_Arr": f"{val_n_arr:.2f}" if val_n_arr > 0 else "", "Niv_Par": f"{val_n_par:.2f}" if val_n_par > 0 else "",
                    "V_L1": int(float(mapa_aux.get(str(info['voltaje_L1']), 0) or 0)), "V_L2": int(float(mapa_aux.get(str(info['voltaje_L2']), 0) or 0)), "V_L3": int(float(mapa_aux.get(str(info['voltaje_L3']), 0) or 0))
                })
    except Exception as e:
        st.error(f"Error de carga: {e}")

# --- VISUALIZACIÓN ---
if lista_apg:
    df_f = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False)
    df_f['Fecha'] = df_f['Fecha'].apply(lambda x: x.strftime('%d/%m/%y'))
    df_f['Hora'] = df_f['Hora'].apply(lambda x: x.strftime('%H:%M:%S'))
    
    def color_text(row):
        estatus = str(row['Estatus_Paro'])
        color = '#FFD700' if '⚠️' in estatus else ('#00FF00' if '✅' in estatus else ('#FF0000' if '❌' in estatus else 'inherit'))
        return [f'color: {color}'] * len(row)

    st.dataframe(df_f.drop(columns=['TS']).style.apply(color_text, axis=1), use_container_width=True, hide_index=True, height=700)
else:
    st.info("Cargando datos o sin pozos apagados.")
