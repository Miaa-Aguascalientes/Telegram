import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, time

st.set_page_config(layout="wide", page_title="Sistema MIAA 24/7")

# --- CONEXIÓN SEGURA ---
@st.cache_resource
def get_engines():
    eng_dic = create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True)
    eng_scada = create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True)
    return eng_dic, eng_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()

# --- LÓGICA DE PROCESAMIENTO ---
st.title("Sistema de Monitoreo MIAA 24/7")

# Consultas para obtener datos
df_dic = pd.read_sql("SELECT Pozos, bomba, H_arranque, H_paro, nivel_tanque, nivel_arranque_tq, nivel_paro_tq, voltaje_L1, voltaje_L2, voltaje_L3 FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
mapa_inc = dict(zip(df_inc['NUM_POZO'].str.replace('-', ''), df_inc['DIAGNOSTICO_FALLA']))

tags_str = "', '".join(df_dic['bomba'].tolist())
query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df = pd.read_sql(query, ENGINE_SCADA)

# Obtener auxiliares (voltajes, niveles)
lista_aux = list(set(df_dic['H_arranque'].tolist() + df_dic['H_paro'].tolist() + df_dic['nivel_tanque'].dropna().tolist() + df_dic['voltaje_L1'].dropna().tolist()))
all_aux_tags = "', '".join(lista_aux)
df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{all_aux_tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'], df_h['VALUE']))

# Bucle principal de clasificación
lista_apg, lista_enc = [], []

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo = info['Pozos']
    inc = mapa_inc.get(pozo.replace('-', ''), "Sin incidencia")
    
    if row['VALUE'] == 0: # APAGADO
        # Aquí aplicamos tu lógica de umbral del 30%
        niv_arr = float(mapa_aux.get(info['nivel_arranque_tq'], 0))
        nivel_val = float(mapa_aux.get(info['nivel_tanque'], 0))
        
        # Clasificación de estatus igual a tu código original
        estatus = "❌ Desconocida"
        if inc.lower() != "sin incidencia": estatus = "⚠️ Parado por incidencia"
        elif nivel_val < (niv_arr * 0.30): estatus = "No arranca por nivel bajo"
        
        lista_apg.append({
            "Pozo": pozo, "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(),
            "Incidencia": inc, "Estatus": estatus, "V_L1": mapa_aux.get(info['voltaje_L1'], 0)
        })
    else: # ENCENDIDO
        lista_enc.append({"Pozo": pozo, "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time()})

# --- VISUALIZACIÓN ---
tab1, tab2 = st.tabs(["APAGADOS", "ENCENDIDOS"])

with tab1:
    df_apg = pd.DataFrame(lista_apg)
    st.dataframe(df_apg, use_container_width=True)

with tab2:
    df_enc = pd.DataFrame(lista_enc)
    st.dataframe(df_enc, use_container_width=True)
