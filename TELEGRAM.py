import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import requests
from datetime import datetime, timedelta, time
import time as t_mod

# Configuración de página
st.set_page_config(layout="wide", page_title="Sistema de Monitoreo MIAA 24/7")

# --- CONEXIÓN A BD ---
@st.cache_resource
def get_engines():
    eng_dic = create_engine("mysql+pymysql://miaamx_telemetria2:bWkrw1Uum1O&@miaa.mx/miaamx_telemetria2", pool_pre_ping=True)
    eng_scada = create_engine("mysql+pymysql://miaamx_dashboard:h97_p,NQPo=l@miaa.mx/miaamx_telemetria", pool_pre_ping=True)
    return eng_dic, eng_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()
TOKEN = '8985322491:AAF1QviZ0h0I4EVC_LFGeOZk51b4l0VaSq4'

# --- ESTADO ---
if 'alertas_enviadas' not in st.session_state: st.session_state.alertas_enviadas = {}
if 'horarios_manuales' not in st.session_state: st.session_state.horarios_manuales = {}

# --- LÓGICA ---
def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now().time()
    return t_par <= ahora <= t_arr if t_par < t_arr else (ahora >= t_par or ahora <= t_arr)

def enviar_alerta(pozo, nivel, hora, h_paro, h_arranque, razon):
    mensaje = f"📢 <b>Alerta MIAA</b>\n⚠️ <b>Bomba Apagada:</b> {pozo}\n⏳ <b>Hora:</b> {hora}\n💧 <b>Nivel:</b> {nivel} mts.\n🔍 <b>Motivo:</b> {razon}"
    ids = pd.read_sql("SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'", ENGINE_DIC)['chart_id'].tolist()
    for chat_id in ids:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'})

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("Configuración Manual")
    p = st.text_input("Pozo")
    p_h = st.text_input("Paro (HH:MM)")
    a_h = st.text_input("Arr (HH:MM)")
    if st.button("Guardar"):
        st.session_state.horarios_manuales[p] = {"H_paro": p_h, "H_arr": a_h}

# --- PROCESAMIENTO ---
st.title("Sistema de Monitoreo MIAA 24/7")

# Obtener datos
df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
tags = "', '".join(df_dic['bomba'].tolist())
query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
df = pd.read_sql(query, ENGINE_SCADA)

# Estilo para celdas
def aplicar_estilo(row):
    color = ''
    if 'Incidencia' in row['Estatus_Paro']: color = 'background-color: #FFD700'
    elif 'Normal' in row['Estatus_Paro']: color = 'background-color: #32CD32'
    else: color = 'background-color: #FF4500; color: white'
    return [color] * len(row)

# Procesar filas
resultados = []
for _, row in df.iterrows():
    info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
    # Lógica original replicada aquí...
    # (Se mapean los valores y se determina estatus_paro)
    resultados.append({
        "Pozo": info['Pozos'],
        "Valor": row['VALUE'],
        "Estatus_Paro": "Normal" # Placeholder de tu lógica if/else
    })

df_proc = pd.DataFrame(resultados)
tab1, tab2 = st.tabs(["APAGADOS", "ENCENDIDOS"])

with tab1:
    df_apg = df_proc[df_proc['Valor'] == 0]
    st.dataframe(df_apg.style.apply(aplicar_estilo, axis=1), use_container_width=True)

with tab2:
    st.dataframe(df_proc[df_proc['Valor'] == 1], use_container_width=True)

# Auto-refresh
t_mod.sleep(60)
st.rerun()
