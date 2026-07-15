import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time, datetime

st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7")

# --- CONEXIÓN ---
@st.cache_resource
def get_engines():
    # Asegúrate de tener estas variables en tus Secrets de Streamlit
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

# Consultas
df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
mapa_inc = dict(zip(df_inc['NUM_POZO'].str.replace('-', ''), df_inc['DIAGNOSTICO_FALLA']))

tags = "', '".join(df_dic['bomba'].tolist())
query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df = pd.read_sql(query, ENGINE_SCADA)

# Auxiliares
lista_aux_tags = "', '".join(list(set(df_dic['H_arranque'].tolist() + df_dic['H_paro'].tolist() + df_dic['nivel_tanque'].dropna().tolist() + df_dic['voltaje_L1'].dropna().tolist())))
df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{lista_aux_tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'], df_h['VALUE']))

lista_apg, lista_enc = [], []

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo = info['Pozos']
    inc = mapa_inc.get(pozo.replace('-', ''), "Sin incidencia")
    
    # Datos comunes
    fila = {
        "Pozo": pozo, "Fecha": row['FECHA'].strftime('%d/%m/%y'), "Hora": row['FECHA'].strftime('%H:%M:%S'),
        "H_paro": convertir_a_hora(mapa_aux.get(info['H_paro'], 0)),
        "H_arranque": convertir_a_hora(mapa_aux.get(info['H_arranque'], 0)),
        "Nivel": float(mapa_aux.get(info['nivel_tanque'], 0)),
        "Niv_Arr": float(mapa_aux.get(info['nivel_arranque_tq'], 0)),
        "Niv_Par": float(mapa_aux.get(info['nivel_paro_tq'], 0)),
        "V_L1": float(mapa_aux.get(info['voltaje_L1'], 0)),
        "V_L2": float(mapa_aux.get(info['voltaje_L2'], 0)),
        "V_L3": float(mapa_aux.get(info['voltaje_L3'], 0))
    }

    if row['VALUE'] == 0:
        # Lógica de Estatus
        estatus = "❌ Desconocida"
        if inc != "Sin incidencia": estatus = "⚠️ Parado por incidencia"
        elif fila['Nivel'] < (fila['Niv_Arr'] * 0.3): estatus = "No arranca con su condición de tanque"
        
        fila["Incidencia"] = inc
        fila["Estatus_Paro"] = estatus
        lista_apg.append(fila)
    else:
        lista_enc.append(fila)

# --- VISUALIZACIÓN ---
tab1, tab2 = st.tabs(["APAGADOS (Atención)", "ENCENDIDOS"])

with tab1:
    if lista_apg:
        df_apg = pd.DataFrame(lista_apg)[["Pozo", "Fecha", "Hora", "Incidencia", "H_paro", "H_arranque", "Nivel", "Niv_Arr", "Niv_Par", "Estatus_Paro", "V_L1", "V_L2", "V_L3"]]
        
        def color_row(val):
            color = ''
            if 'incidencia' in str(val).lower(): color = '#FFD700'
            elif 'desconocida' in str(val).lower(): color = '#FF4500'
            elif 'no arranca' in str(val).lower(): color = '#FF4500'
            return f'background-color: {color}; color: black'

        # Usamos .map en lugar de applymap para compatibilidad con versiones nuevas
        st.dataframe(df_apg.style.map(color_row, subset=['Estatus_Paro']), use_container_width=True)
    else:
        st.info("No hay pozos apagados actualmente.")

with tab2:
    if lista_enc:
        st.dataframe(pd.DataFrame(lista_enc), use_container_width=True)
    else:
        st.info("No hay pozos encendidos.")
