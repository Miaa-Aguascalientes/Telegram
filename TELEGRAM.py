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
try:
    df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada' ORDER BY FECHA_INICIO DESC", ENGINE_SCADA)
    mapa_inc = dict(zip(df_inc['NUM_POZO'].str.replace('-', ''), df_inc['DIAGNOSTICO_FALLA']))
except:
    mapa_inc = {}

# Carga de datos SCADA
tags = "', '".join(df_dic['bomba'].tolist())
query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df = pd.read_sql(query, ENGINE_SCADA)

# Carga de auxiliares (Aseguramos que buscamos por nombre exacto)
cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
tags_aux = [str(t) for col in cols_aux for t in df_dic[col].dropna().unique()]
query_aux = f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df_h = pd.read_sql(query_aux, ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

# DEBUG: Verificar si el mapa tiene datos
if not mapa_aux:
    st.error("No se encontraron valores para los tags auxiliares en SCADA. Revisa que los nombres de los tags en el Diccionario coincidan con los de SCADA.")

lista_apg, lista_enc = [], []

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo = info['Pozos']
    inc = mapa_inc.get(pozo.replace('-', ''), "Sin incidencia")
    
    # Función segura para obtener datos (evita el 0 por defecto si no existe)
    def get_val(col_name):
        tag = info.get(col_name)
        return mapa_aux.get(str(tag)) if pd.notna(tag) else None

    v1, v2, v3 = get_val('voltaje_L1'), get_val('voltaje_L2'), get_val('voltaje_L3')
    nivel = get_val('nivel_tanque')
    
    fila = {
        "Pozo": pozo, "Fecha": row['FECHA'].strftime('%d/%m/%y'), "Hora": row['FECHA'].strftime('%H:%M:%S'),
        "Incidencia": inc,
        "H_paro": convertir_a_hora(get_val('H_paro')),
        "H_arranque": convertir_a_hora(get_val('H_arranque')),
        "Nivel": f"{float(nivel):.2f}" if nivel is not None else "N/A",
        "Niv_Arr": f"{float(get_val('nivel_arranque_tq')):.2f}" if get_val('nivel_arranque_tq') is not None else "N/A",
        "Niv_Par": f"{float(get_val('nivel_paro_tq')):.2f}" if get_val('nivel_paro_tq') is not None else "N/A",
        "V_L1": int(float(v1)) if v1 is not None else "N/A",
        "V_L2": int(float(v2)) if v2 is not None else "N/A",
        "V_L3": int(float(v3)) if v3 is not None else "N/A"
    }

    if row['VALUE'] == 0:
        fila["Estatus_Paro"] = "⚠️ Parado por incidencia" if inc != "Sin incidencia" else "❌ Desconocida"
        lista_apg.append(fila)
    else:
        lista_enc.append(fila)

# --- VISUALIZACIÓN ---
tab1, tab2 = st.tabs(["APAGADOS (Atención)", "ENCENDIDOS"])
with tab1:
    if lista_apg:
        st.dataframe(pd.DataFrame(lista_apg), use_container_width=True)
with tab2:
    if lista_enc:
        st.dataframe(pd.DataFrame(lista_enc), use_container_width=True)
