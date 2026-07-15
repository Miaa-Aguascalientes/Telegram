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

# Carga de Incidencias
try:
    query_inc = "SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'"
    df_inc = pd.read_sql(query_inc, ENGINE_SCADA)
    df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
    mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
except:
    mapa_inc = {}

# Carga de Datos SCADA
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

# Carga de Auxiliares
cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
tags_aux = [str(t) for col in cols_aux for t in df_dic[col].dropna().unique()]
query_aux = f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df_h = pd.read_sql(query_aux, ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

lista_apg = []

def format_val(v):
    return f"{v:.2f}" if v > 0 else ""

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
    inc = mapa_inc.get(pozo_key, "Sin incidencia")
    
    val_nivel = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
    val_n_arr = float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0)
    val_n_par = float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)
    
    if row['VALUE'] == 0:
        if inc != "Sin incidencia":
            estatus = f"⚠️ {inc}"
        elif val_n_arr > 0 and val_n_par > 0:
            estatus = "✅ Normal" if (val_nivel >= val_n_arr or (val_n_par > val_nivel > val_n_arr)) else "❌ Desconocida"
        else:
            estatus = "❌ Desconocida"
        
        lista_apg.append({
            "Estatus_Paro": estatus,
            "Pozo": info['Pozos'], 
            "Fecha": row['FECHA'].strftime('%d/%m/%y'), 
            "Hora": row['FECHA'].strftime('%H:%M:%S'),
            "Incidencia": inc,
            "H_paro": convertir_a_hora(mapa_aux.get(str(info['H_paro']))),
            "H_arranque": convertir_a_hora(mapa_aux.get(str(info['H_arranque']))),
            "Nivel": format_val(val_nivel),
            "Niv_Arr": format_val(val_n_arr),
            "Niv_Par": format_val(val_n_par),
            "V_L1": int(float(mapa_aux.get(str(info['voltaje_L1']), 0) or 0)),
            "V_L2": int(float(mapa_aux.get(str(info['voltaje_L2']), 0) or 0)),
            "V_L3": int(float(mapa_aux.get(str(info['voltaje_L3']), 0) or 0))
        })

# --- VISUALIZACIÓN ---
if lista_apg:
    df_final = pd.DataFrame(lista_apg)
    
    def color_text(row):
        estatus = str(row['Estatus_Paro'])
        # Colores intensos: Amarillo brillante, Verde neón, Rojo intenso
        if '⚠️' in estatus: color = '#FFD700' 
        elif '✅' in estatus: color = '#00FF00' 
        elif '❌' in estatus: color = '#FF0000' 
        else: color = 'inherit'
        return [f'color: {color}'] * len(row)

    st.dataframe(
        df_final.style.apply(color_text, axis=1), 
        use_container_width=True, 
        hide_index=True
    )
else:
    st.info("No hay pozos apagados.")
