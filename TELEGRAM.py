import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import requests
from datetime import datetime, timedelta, time

# Configuración de página
st.set_page_config(layout="wide", page_title="Monitoreo MIAA")

# --- CONEXIÓN A BD ---
@st.cache_resource
def get_engines():
    eng_dic = create_engine("mysql+pymysql://miaamx_telemetria2:bWkrw1Uum1O&@miaa.mx/miaamx_telemetria2", pool_pre_ping=True)
    eng_scada = create_engine("mysql+pymysql://miaamx_dashboard:h97_p,NQPo=l@miaa.mx/miaamx_telemetria", pool_pre_ping=True)
    return eng_dic, eng_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()
TOKEN = '8985322491:AAF1QviZ0h0I4EVC_LFGeOZk51b4l0VaSq4'

# Inicializar estado para alertas
if 'alertas_enviadas' not in st.session_state: st.session_state.alertas_enviadas = {}

# --- LÓGICA DE NEGOCIO ---
def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now().time()
    return t_par <= ahora <= t_arr if t_par < t_arr else (ahora >= t_par or ahora <= t_arr)

def enviar_alerta(pozo, nivel, razon):
    mensaje = f"⚠️ <b>Alerta MIAA:</b> {pozo}\n💧 <b>Nivel:</b> {nivel}\n🔍 <b>Motivo:</b> {razon}"
    ids = pd.read_sql("SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'", ENGINE_DIC)['chart_id'].tolist()
    for chat_id in ids:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)

# --- INTERFAZ ---
st.title("Sistema de Monitoreo MIAA 24/7")

# Obtener datos (puedes usar @st.cache_data para no consultar a cada rato)
@st.cache_data(ttl=60)
def cargar_datos():
    df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
    # ... (Aquí incluyes tus consultas SQL exactamente como en tu script original)
    return df_dic

# Procesamiento de filas (Ciclo principal)
# Aquí replicas tu bucle 'for _, row in df.iterrows():' del archivo original
# Y construyes dos listas: una para apagados y otra para encendidos

tab1, tab2 = st.tabs(["APAGADOS", "ENCENDIDOS"])

with tab1:
    st.subheader("APAGADOS (Atención)")
    # df_apg = pd.DataFrame(datos_apagados)
    # st.dataframe(df_apg) 
    st.info("Aquí se mostrará tu tabla de apagados con colores.")

with tab2:
    st.subheader("ENCENDIDOS")
    # df_enc = pd.DataFrame(datos_encendidos)
    # st.dataframe(df_enc)

# Botón de actualización manual
if st.button("Forzar actualización"):
    st.rerun()
