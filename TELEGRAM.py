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
except Exception as e:
    st.error(f"Error al cargar incidencias: {e}")
    mapa_inc = {}

# Carga de SCADA
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

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
    inc = mapa_inc.get(pozo_key, "Sin incidencia")
    
    def get_val(c): return mapa_aux.get(str(info.get(c)))
    
    val_nivel = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
    val_n_arr = float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0)
    val_n_par = float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)
    
    # Aseguramos que la comparación sea contra float explícito
    nv = float(val_nivel)
    arr = float(val_n_arr)
    par = float(val_n_par)

    if row['VALUE'] == 0:
        # 1. Prioridad: Incidencia registrada
        if inc != "Sin incidencia":
            estatus = "⚠️ Parado por incidencia"
        # 2. Si no hay incidencia, verificamos si existe configuración de niveles (arr > 0 y par > 0)
        elif arr > 0 and par > 0:
            if nv >= arr or (par > nv > arr):
                estatus = "✅ Normal"
            else:
                estatus = "❌ Desconocida"
        # 3. Si no hay niveles y tampoco incidencia, es Desconocida
        else:
            estatus = "❌ Desconocida"
        
        lista_apg.append({
            "Pozo": info['Pozos'], 
            "Fecha": row['FECHA'].strftime('%d/%m/%y'), 
            "Hora": row['FECHA'].strftime('%H:%M:%S'),
            "Incidencia": inc,
            "H_paro": convertir_a_hora(get_val('H_paro')),
            "H_arranque": convertir_a_hora(get_val('H_arranque')),
            # Aplicamos el formato para ocultar ceros
            "Nivel": format_val(val_nivel),
            "Niv_Arr": format_val(val_n_arr),
            "Niv_Par": format_val(val_n_par),
            "Estatus_Paro": estatus,
            "V_L1": int(float(get_val('voltaje_L1') or 0)),
            "V_L2": int(float(get_val('voltaje_L2') or 0)),
            "V_L3": int(float(get_val('voltaje_L3') or 0))
        })

# --- VISUALIZACIÓN ---
if lista_apg:
    df_final = pd.DataFrame(lista_apg)
    
    def color_row(val):
        v = str(val)
        if 'Parado por incidencia' in v: return 'background-color: #FFD700; color: black'
        if 'Normal' in v: return 'background-color: #2E7D32; color: white'
        if 'Desconocida' in v: return 'background-color: #D32F2F; color: white'
        return ''

    st.dataframe(df_final.style.map(color_row, subset=['Estatus_Paro']), use_container_width=True)
else:
    st.info("No hay pozos apagados.")
