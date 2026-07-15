import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time

st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7")

# --- CONEXIÓN ---
@st.cache_resource
def get_engines():
    eng_dic = create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True, pool_recycle=1800)
    eng_scada = create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True, pool_recycle=1800)
    return eng_dic, eng_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

# --- PROCESAMIENTO ---
st.title("Sistema de Monitoreo MIAA 24/7")

df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)

# 1. Incidencias con orden DESC para obtener las más recientes primero
try:
    query_inc = "SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada' ORDER BY FECHA_INICIO DESC"
    df_inc = pd.read_sql(query_inc, ENGINE_SCADA)
    df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
    mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
except:
    mapa_inc = {}

# 2. Datos SCADA ordenados por fecha (MÁS RECIENTES PRIMERO)
tags = "', '".join(df_dic['bomba'].tolist())
query = f"""
SELECT r.NAME, h.VALUE, h.FECHA 
FROM VfiTagNumHistory_Ultimo h 
JOIN VfiTagRef r ON h.GATEID = r.GATEID 
WHERE r.NAME IN ('{tags}') 
AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)
ORDER BY h.FECHA DESC
"""
df = pd.read_sql(query, ENGINE_SCADA)

# 3. Auxiliares
cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
tags_aux = [str(t) for col in cols_aux for t in df_dic[col].dropna().unique()]
query_aux = f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df_h = pd.read_sql(query_aux, ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

lista_apg = []

# Iterar sobre el DataFrame ya ordenado
for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
    inc = mapa_inc.get(pozo_key, "Sin incidencia")
    
    def get_val(c): return mapa_aux.get(str(info.get(c)))
    
    val_nivel = get_val('nivel_tanque')
    val_n_arr = get_val('nivel_arranque_tq')
    val_n_par = get_val('nivel_paro_tq')
    
    if row['VALUE'] == 0:
        estatus = "❌ Desconocida"
        if inc != "Sin incidencia": estatus = f"⚠️ {inc}"
        elif val_nivel is not None and val_n_arr is not None and float(val_nivel) < (float(val_n_arr) * 0.3):
            estatus = "No arranca con su condición de tanque"
        
        lista_apg.append({
            "Pozo": info['Pozos'], 
            "Fecha": row['FECHA'].strftime('%d/%m/%y'), 
            "Hora": row['FECHA'].strftime('%H:%M:%S'),
            "Incidencia": inc,
            "H_paro": convertir_a_hora(get_val('H_paro')),
            "H_arranque": convertir_a_hora(get_val('H_arranque')),
            "Nivel": f"{float(val_nivel):.2f}" if val_nivel is not None else "0.00",
            "Niv_Arr": f"{float(val_n_arr):.2f}" if val_n_arr is not None else "0.00",
            "Niv_Par": f"{float(val_n_par):.2f}" if val_n_par is not None else "0.00",
            "Estatus_Paro": estatus,
            "V_L1": int(float(get_val('voltaje_L1') or 0)),
            "V_L2": int(float(get_val('voltaje_L2') or 0)),
            "V_L3": int(float(get_val('voltaje_L3') or 0))
        })

# --- VISUALIZACIÓN ---
if lista_apg:
    df_final = pd.DataFrame(lista_apg)
    def color_row(val):
        v = str(val).lower()
        if 'incidencia' in v or 'fuga' in v or 'desgaste' in v or 'abierto' in v or 'preventivo' in v: return 'background-color: #FFD700; color: black'
        if 'desconocida' in v: return 'background-color: #FF4500; color: black'
        return ''

    st.dataframe(df_final.style.map(color_row, subset=['Estatus_Paro']), use_container_width=True)
else:
    st.info("No hay pozos apagados.")
