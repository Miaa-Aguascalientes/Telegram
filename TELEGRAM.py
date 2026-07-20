import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time, datetime, timedelta
import time as t
import threading
import requests
from zoneinfo import ZoneInfo

# Configuración de página
st.set_page_config(layout="wide", page_title="Sistema de monitoreo", page_icon="https://www.miaa.mx/favicon.ico")

# --- ESTADO DE SESIÓN ---
if 'alertas_enviadas' not in st.session_state: st.session_state.alertas_enviadas = {}
if 'logs' not in st.session_state: st.session_state.logs = []
if 'alertas_activas' not in st.session_state: st.session_state.alertas_activas = False
if 'busqueda_pozo' not in st.session_state: st.session_state.busqueda_pozo = ""

zona_mx = ZoneInfo("America/Mexico_City")

# --- FUNCIONES ---
def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now(zona_mx).time()
    if t_par < t_arr: return t_par <= ahora <= t_arr
    else: return ahora >= t_par or ahora <= t_arr

def enviar_alerta(pozo, nivel, nivel_arr, hora_alerta, h_paro, h_arranque, razon, hora_paro):
    token = st.secrets["telegram"]["token"]
    mensaje = f"📢 <b>Reporte Automatico Miaa</b>\n________________________________\n⚠️ <b>Alerta:</b> Bomba Apagada\n📍 <b>Pozo:</b> {pozo}\n⏳ <b>Hora del paro:</b> {hora_paro}\n💧 <b>Nivel Tanque:</b> {nivel} mts.\n↕️ <b>Nivel Arranque con TQ:</b> {nivel_arr} mts.\n⏲️ <b>Horario de Op:</b> {h_paro} - {h_arranque}\n🔍 <b>Motivo:</b> {razon}"
    def send():
        try:
            df_ids = pd.read_sql("SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'", ENGINE_DIC)
            for chat_id in df_ids['chart_id'].tolist(): requests.get(f"https://api.telegram.org/bot{token}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
        except: pass
    threading.Thread(target=send, daemon=True).start()
    st.session_state.logs.append(f"[{datetime.now(zona_mx).strftime('%H:%M:%S')}] Alerta enviada: {pozo} - {razon} (Paro: {hora_paro})")

# --- CSS ---
st.write("""<style>#MainMenu, header {visibility: hidden;} .block-container {padding-top: 0rem !important; padding-bottom: 0rem !important;} .custom-title {color: #00E5FF !important; font-size: 2rem; font-weight: bold; margin-bottom: 0px; text-align: center; margin-top: 0px;} .log-console {background-color: #0e1117; color: #00FF00; font-family: monospace; padding: 10px; border: 1px solid #003366; border-radius: 5px; height: 150px; overflow-y: scroll; font-size: 0.85rem;}</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_engines(): return create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True, pool_recycle=1800), create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True, pool_recycle=1800)
ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try: m = float(valor); return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

# --- CABECERA ---
col_h1, col_h2 = st.columns([1, 10])
with col_h1: st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=150)
with col_h2: st.markdown('<h1 class="custom-title">Sistema de Monitoreo</h1>', unsafe_allow_html=True)

st.toggle("Activar envío de alertas a Telegram", key="alertas_activas") 

# --- ESTRUCTURA ORIGINAL ---
col_izq, col_der = st.columns([0.65, 0.35])

# --- CONTENEDORES PARA LAS TABLAS QUE SE REFRESCA ---
table_apg = col_izq.empty()
table_enc = col_der.empty()
log_area = st.empty()

# Encabezados estáticos
with col_izq: st.subheader("🔴 Pozos Apagados")
with col_der: 
    st.subheader("🟢 Pozos Encendidos")
    st.text_input("🔍 Buscar pozo...", key='busqueda_pozo')

while True:
    # --- LÓGICA DE DATOS ---
    df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
    # ... (aquí va tu lógica de lectura de BD igual a como la tenías)
    df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
    df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
    mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
    
    tags = "', '".join(df_dic['bomba'].tolist())
    df = pd.read_sql(f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
    tags_aux = [str(t) for col in ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3'] for t in df_dic[col].dropna().unique()]
    df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
    mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

    lista_apg, lista_enc = [], []
    ahora_actual = datetime.now(zona_mx)

    for _, row in df.iterrows():
        # ... (Tu bucle de procesamiento de lista_apg y lista_enc)
        # (He omitido el código aquí por brevedad, usa exactamente el mismo que tenías)
        pass 

    df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False) if lista_apg else pd.DataFrame()
    df_enc_full = pd.DataFrame(lista_enc).sort_values(by='Fecha', ascending=False) if lista_enc else pd.DataFrame()
    
    # --- DIBUJADO DE TABLAS EN SUS SITIOS ORIGINALES ---
    with table_apg:
        if not df_final.empty:
            # (Tu función color_fila aquí)
            st.dataframe(df_final.drop(columns=['TS']).style.apply(color_fila, axis=1), use_container_width=True, hide_index=True)
    
    with table_enc:
        df_mostrar = df_enc_full
        if st.session_state.busqueda_pozo:
            df_mostrar = df_enc_full[df_enc_full['Pozo'].astype(str).str.contains(st.session_state.busqueda_pozo, case=False, na=False)]
        if not df_mostrar.empty: st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

    with log_area:
        st.subheader("📋 Registro de Alertas")
        st.markdown(f'<div class="log-console">{"<br>".join(reversed(st.session_state.logs))}</div>', unsafe_allow_html=True)
    
    t.sleep(30)
