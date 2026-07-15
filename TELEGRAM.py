import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time, datetime

st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7")

@st.cache_resource
def get_engines():
    eng_dic = create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True, pool_recycle=1800)
    eng_scada = create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True, pool_recycle=1800)
    return eng_dic, eng_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try:
        return time(int((float(valor) // 60) % 24), int(float(valor) % 60))
    except: return time(0, 0)

st.title("Sistema de Monitoreo MIAA 24/7")

df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
try:
    df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada' ORDER BY FECHA_INICIO DESC", ENGINE_SCADA)
    mapa_inc = dict(zip(df_inc['NUM_POZO'].str.replace('-', ''), df_inc['DIAGNOSTICO_FALLA']))
except:
    mapa_inc = {}

tags = "', '".join(df_dic['bomba'].tolist())
df = pd.read_sql(f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)

cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
lista_aux_tags = list(set([t for col in cols_aux for t in df_dic[col].dropna().tolist()]))
df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{', '.join([f'\"{t}\"' for t in lista_aux_tags])}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'], df_h['VALUE']))

lista_apg, lista_enc = [], []

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo = info['Pozos']
    inc = mapa_inc.get(pozo.replace('-', ''), "Sin incidencia")
    
    # Obtener valores crudos primero
    val_nivel = mapa_aux.get(info['nivel_tanque'], 0)
    val_n_arr = mapa_aux.get(info['nivel_arranque_tq'], 0)
    v1 = mapa_aux.get(info['voltaje_L1'], None)
    v2 = mapa_aux.get(info['voltaje_L2'], None)
    v3 = mapa_aux.get(info['voltaje_L3'], None)
    
    fila = {
        "Pozo": pozo, "Fecha": row['FECHA'].strftime('%d/%m/%y'), "Hora": row['FECHA'].strftime('%H:%M:%S'),
        "Incidencia": inc,
        "H_paro": convertir_a_hora(mapa_aux.get(info['H_paro'], 0)),
        "H_arranque": convertir_a_hora(mapa_aux.get(info['H_arranque'], 0)),
        "Nivel": f"{float(val_nivel):.2f}",
        "Niv_Arr": f"{float(val_n_arr):.2f}",
        "Niv_Par": f"{float(mapa_aux.get(info['nivel_paro_tq'], 0)):.2f}",
        "V_L1": int(float(v1)) if v1 is not None else 0,
        "V_L2": int(float(v2)) if v2 is not None else 0,
        "V_L3": int(float(v3)) if v3 is not None else 0
    }

    if row['VALUE'] == 0:
        estatus = "❌ Desconocida"
        if inc != "Sin incidencia": estatus = "⚠️ Parado por incidencia"
        elif float(val_nivel) < (float(val_n_arr) * 0.3): estatus = "No arranca con su condición de tanque"
        fila["Estatus_Paro"] = estatus
        lista_apg.append(fila)
    else:
        lista_enc.append(fila)

with st.tabs(["APAGADOS (Atención)", "ENCENDIDOS"])[0]:
    if lista_apg:
        df_apg = pd.DataFrame(lista_apg)
        def color_row(val):
            color = '#FFD700' if 'incidencia' in str(val).lower() else '#FF4500'
            return f'background-color: {color}; color: black'
        st.dataframe(df_apg.style.map(color_row, subset=['Estatus_Paro']), use_container_width=True)
    else:
        st.info("No hay pozos apagados.")
