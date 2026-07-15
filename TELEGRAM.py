import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, time

st.set_page_config(layout="wide", page_title="Sistema MIAA")

# --- CONEXIÓN SEGURA ---
@st.cache_resource
def get_engines():
    eng_dic = create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True)
    eng_scada = create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True)
    return eng_dic, eng_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()

# --- FUNCIONES AUXILIARES ---
def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now().time()
    return t_par <= ahora <= t_arr if t_par < t_arr else (ahora >= t_par or ahora <= t_arr)

# --- PROCESAMIENTO ---
st.title("Sistema de Monitoreo MIAA 24/7")

# 1. Carga de Diccionarios e Incidencias
df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
mapa_inc = dict(zip(df_inc['NUM_POZO'].str.replace('-', ''), df_inc['DIAGNOSTICO_FALLA']))

# 2. Carga de datos de telemetría
tags_str = "', '".join(df_dic['bomba'].tolist())
query_tele = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df = pd.read_sql(query_tele, ENGINE_SCADA)

# 3. Carga de auxiliares (niveles/voltajes)
lista_aux = list(set(df_dic['H_arranque'].tolist() + df_dic['H_paro'].tolist() + df_dic['nivel_tanque'].dropna().tolist() + df_dic['voltaje_L1'].dropna().tolist()))
all_aux_tags = "', '".join(lista_aux)
df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{all_aux_tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
mapa_aux = dict(zip(df_h['NAME'], df_h['VALUE']))

# 4. Clasificación
lista_apg, lista_enc = [], []

for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    pozo_nombre = info['Pozos']
    
    # Cálculo de estatus (Lógica original)
    if row['VALUE'] == 0:
        inc = mapa_inc.get(pozo_nombre.replace('-', ''), "Sin incidencia")
        # Aquí insertas tu lógica de if/else de estatus_paro...
        estatus = "⚠️ Paro" if inc != "Sin incidencia" else "❌ Desconocida"
        
        lista_apg.append({"Pozo": pozo_nombre, "Estatus": estatus, "Incidencia": inc, "Hora": row['FECHA'].strftime('%H:%M:%S')})
    else:
        lista_enc.append({"Pozo": pozo_nombre, "Hora": row['FECHA'].strftime('%H:%M:%S')})

# --- VISUALIZACIÓN ---
tab1, tab2 = st.tabs(["APAGADOS", "ENCENDIDOS"])

with tab1:
    df_apg = pd.DataFrame(lista_apg)
    if not df_apg.empty:
        st.dataframe(df_apg, use_container_width=True)
    else:
        st.success("No hay pozos apagados.")

with tab2:
    st.dataframe(pd.DataFrame(lista_enc), use_container_width=True)
