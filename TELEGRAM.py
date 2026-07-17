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

zona_mx = ZoneInfo("America/Mexico_City")

# --- FUNCIONES ---
def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now(zona_mx).time()
    if t_par < t_arr: return t_par <= ahora <= t_arr
    else: return ahora >= t_par or ahora <= t_arr

def enviar_alerta(pozo, nivel, nivel_arr, hora, h_paro, h_arranque, razon):
    token = st.secrets["telegram"]["token"]
    mensaje = f"📢 <b>Reporte Automatico Miaa</b>\n________________________________\n⚠️ <b>Alerta:</b> Bomba Apagada\n📍 <b>Pozo:</b> {pozo}\n⏳ <b>Hora del paro:</b> {hora}\n💧 <b>Nivel Tanque:</b> {nivel} mts.\n↕️ <b>Nivel Arranque con TQ:</b> {nivel_arr} mts.\n⏲️ <b>Horario de Op:</b> {h_paro} - {h_arranque}\n🔍 <b>Motivo:</b> {razon}"
    def send():
        try:
            df_ids = pd.read_sql("SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'", ENGINE_DIC)
            for chat_id in df_ids['chart_id'].tolist(): requests.get(f"https://api.telegram.org/bot{token}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
        except: pass
    threading.Thread(target=send, daemon=True).start()
    st.session_state.logs.append(f"[{datetime.now(zona_mx).strftime('%H:%M:%S')}] Alerta enviada: {pozo} - {razon}")

# --- CSS ---
st.write("""<style>#MainMenu, header {visibility: hidden;} .log-console {background-color: #0e1117; color: #00FF00; font-family: monospace; padding: 10px; border: 1px solid #003366; border-radius: 5px; height: 150px; overflow-y: scroll; font-size: 0.85rem;}</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_engines(): return create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True, pool_recycle=1800), create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True, pool_recycle=1800)
ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try: m = float(valor); return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

col_h1, col_h2 = st.columns([1, 10])
with col_h1: st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=150)
with col_h2: st.markdown('<h1 style="color: #00E5FF; text-align: center;">Sistema de Monitoreo</h1>', unsafe_allow_html=True)

placeholder = st.empty()
while True:
    with placeholder.container():
        df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
        try:
            df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
            df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
            mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
        except: mapa_inc = {}

        tags = "', '".join(df_dic['bomba'].tolist())
        df = pd.read_sql(f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
        df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join([str(t) for col in ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3'] for t in df_dic[col].dropna().unique()])}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
        mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

        lista_apg, lista_enc = [], []
        ahora_dt = datetime.now(zona_mx)

        for _, row in df.iterrows():
            df_match = df_dic[df_dic['bomba'] == row['NAME']]
            if df_match.empty: continue
            info = df_match.iloc[0]
            inc = mapa_inc.get(str(info['Pozos']).replace('-', '').replace(' ', ''), "Sin incidencia")
            n_tq, n_arr, n_par = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0), float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0), float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)
            fecha_bd = row['FECHA'].tz_localize(None).replace(tzinfo=zona_mx) if row['FECHA'].tzinfo is None else row['FECHA'].astimezone(zona_mx)
            
            if row['VALUE'] == 0:
                estatus, razon = ("⚠️ Parado por incidencia", inc) if inc != "Sin incidencia" else (("✅ Normal", "Operación normal") if (es_periodo_de_paro_programado(convertir_a_hora(mapa_aux.get(str(info['H_paro']))), convertir_a_hora(mapa_aux.get(str(info['H_arranque'])))) or (n_tq >= n_par and n_par > 0) or (n_tq >= (n_arr * 0.30) and n_tq < n_par)) else (("No arranca con su condición de tanque", "Nivel bajo") if n_tq < (n_arr * 0.30) and n_arr > 0 else ("❌ Desconocida", "Estatus desconocido")))
                
                # --- VALIDACIÓN CRÍTICA AQUÍ ---
                if (st.session_state.alertas_activas and inc == "Sin incidencia" and razon != "Operación normal" and (ahora_dt - fecha_bd) > timedelta(minutes=90) and info['Pozos'] not in st.session_state.alertas_enviadas):
                    enviar_alerta(info['Pozos'], f"{n_tq:.2f}", f"{n_arr:.2f}", row['FECHA'].time(), convertir_a_hora(mapa_aux.get(str(info['H_paro']))), convertir_a_hora(mapa_aux.get(str(info['H_arranque']))), razon)
                    st.session_state.alertas_enviadas[info['Pozos']] = ahora_dt
                
                lista_apg.append({"Pozo": info['Pozos'], "Estatus_Paro": estatus, "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(), "Incidencia": inc, "Nivel_Tanque": f"{n_tq:.2f}" if n_tq > 0 else "Directo a red", "Nivel_Arranque": f"{n_arr:.2f}" if n_arr > 0 else "", "Nivel_Paro": f"{n_par:.2f}" if n_par > 0 else "", "V_L1": f"{float(mapa_aux.get(str(info['voltaje_L1']), 0)):.2f}", "V_L2": f"{float(mapa_aux.get(str(info['voltaje_L2']), 0)):.2f}", "V_L3": f"{float(mapa_aux.get(str(info['voltaje_L3']), 0)):.2f}", "TS": row['FECHA']})
            else:
                if info['Pozos'] in st.session_state.alertas_enviadas: del st.session_state.alertas_enviadas[info['Pozos']]
                lista_enc.append({"Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time()})

        df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False) if lista_apg else pd.DataFrame()
        df_enc_full = pd.DataFrame(lista_enc).sort_values(by='Fecha', ascending=False) if lista_enc else pd.DataFrame()
        
        # Renderizado final
        st.markdown("<hr>", unsafe_allow_html=True)
        st.toggle("Activar envío de alertas a Telegram", key="alertas_activas") 
        st.subheader("📋 Registro de Alertas")
        st.markdown(f'<div class="log-console">{"<br>".join(reversed(st.session_state.logs))}</div>', unsafe_allow_html=True)
        
        col_izq, col_der = st.columns([0.65, 0.35])
        with col_izq: 
            st.subheader("🔴 Pozos Apagados")
            if not df_final.empty: st.dataframe(df_final.drop(columns=['TS']).style.apply(lambda r: [f'color: {"#FFD700" if "⚠️" in str(r["Estatus_Paro"]) else ("#00FF00" if "✅" in str(r["Estatus_Paro"]) else ("#FF0000" if "❌" in str(r["Estatus_Paro"]) else "inherit"))}'] * len(r), axis=1).set_properties(**{'text-align': 'center'}, subset=['Nivel_Tanque', 'Nivel_Arranque', 'Nivel_Paro', 'V_L1', 'V_L2', 'V_L3']), use_container_width=True, hide_index=True)
        with col_der: 
            st.subheader("🟢 Pozos Encendidos")
            if not df_enc_full.empty: st.dataframe(df_enc_full, use_container_width=True, hide_index=True)
    t.sleep(30)
