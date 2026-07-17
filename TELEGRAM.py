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
if 'alertas_enviadas' not in st.session_state:
    st.session_state.alertas_enviadas = {}
if 'logs' not in st.session_state:
    st.session_state.logs = []

zona_mx = ZoneInfo("America/Mexico_City")

# --- FUNCIONES DE TELEGRAM ---
def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now(zona_mx).time()
    if t_par < t_arr: return t_par <= ahora <= t_arr
    else: return ahora >= t_par or ahora <= t_arr

def enviar_alerta(pozo, nivel, nivel_arr, hora, h_paro, h_arranque, razon):
    token = st.secrets["telegram"]["token"]
    mensaje = (
        f"📢 <b>Reporte Automatico Miaa</b>\n"
        f"________________________________\n"
        f"⚠️ <b>Alerta:</b> Bomba Apagada\n"
        f"📍 <b>Pozo:</b> {pozo}\n"
        f"⏳ <b>Hora del paro:</b> {hora}\n"
        f"💧 <b>Nivel Tanque:</b> {nivel} mts.\n"
        f"↕️ <b>Nivel Arranque con TQ:</b> {nivel_arr} mts.\n"           
        f"⏲️ <b>Horario de Op:</b> {h_paro} - {h_arranque}\n"
        f"🔍 <b>Motivo:</b> {razon}"
    )
    def send():
        try:
            query = "SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'"
            df_ids = pd.read_sql(query, ENGINE_DIC)
            for chat_id in df_ids['chart_id'].tolist():
                try:
                    requests.get(f"https://api.telegram.org/bot{token}/sendMessage", 
                                 params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
                except: continue
        except: pass
    threading.Thread(target=send, daemon=True).start()
    st.session_state.logs.append(f"[{datetime.now(zona_mx).strftime('%H:%M:%S')}] Alerta enviada: {pozo} - {razon}")

# --- CSS ---
st.write("""
<style>
    #MainMenu, header {visibility: hidden;}
    .block-container {padding-top: 0.2rem !important; padding-bottom: 0rem !important;}
    .custom-title {color: #00E5FF !important; font-size: 2rem; font-weight: bold; margin-bottom: 5px; text-align: center;}
    .dashboard-card {
        background: linear-gradient(135deg, #1e2630 0%, #0e1117 100%);
        border: 2px solid #003366; border-radius: 8px; padding: 4px 8px !important; text-align: center; margin: 2px !important;
        display: flex; justify-content: space-between; align-items: center;
    }
    .card-label {color: #ffffff; font-size: 0.85rem !important; font-weight: 500; margin: 0 !important;}
    .card-value {font-size: 1rem !important; font-weight: bold; margin-left: 10px;}
    .log-console {
        background-color: #0e1117; color: #00FF00; font-family: monospace; padding: 10px; 
        border: 1px solid #003366; border-radius: 5px; height: 150px; overflow-y: scroll; font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

def render_card(label, value, color_val, icon):
    st.write(f'<div class="dashboard-card"><div class="card-label">{icon} {label}</div><div class="card-value" style="color: {color_val}">{value}</div></div>', unsafe_allow_html=True)

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

col_h1, col_h2 = st.columns([1, 10])
with col_h1: st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=150)
with col_h2: st.markdown('<h1 class="custom-title">Sistema de Monitoreo</h1>', unsafe_allow_html=True)



placeholder = st.empty()

while True:
    with placeholder.container():
        df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
        try:
            query_inc = "SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'"
            df_inc = pd.read_sql(query_inc, ENGINE_SCADA)
            df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
            mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
        except: mapa_inc = {}

        tags = "', '".join(df_dic['bomba'].tolist())
        query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
        df = pd.read_sql(query, ENGINE_SCADA)

        cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
        tags_aux = [str(t) for col in cols_aux for t in df_dic[col].dropna().unique()]
        query_aux = f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
        df_h = pd.read_sql(query_aux, ENGINE_SCADA)
        mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

        lista_apg, lista_enc = [], []
        ahora_dt = datetime.now(zona_mx)

        for _, row in df.iterrows():
            df_match = df_dic[df_dic['bomba'] == row['NAME']]
            if df_match.empty: continue
            info = df_match.iloc[0]
            pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
            inc = mapa_inc.get(pozo_key, "Sin incidencia")
            
            n_tq = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
            n_arr = float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0)
            n_par = float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)
            h_p = convertir_a_hora(mapa_aux.get(str(info['H_paro'])))
            h_a = convertir_a_hora(mapa_aux.get(str(info['H_arranque'])))
            v1 = mapa_aux.get(str(info['voltaje_L1']), 0)
            v2 = mapa_aux.get(str(info['voltaje_L2']), 0)
            v3 = mapa_aux.get(str(info['voltaje_L3']), 0)
            
            fecha_bd = row['FECHA'].tz_localize(None).replace(tzinfo=zona_mx) if row['FECHA'].tzinfo is None else row['FECHA'].astimezone(zona_mx)

            if row['VALUE'] == 0:
                if inc != "Sin incidencia": estatus, razon = "⚠️ Parado por incidencia", inc
                elif es_periodo_de_paro_programado(h_p, h_a) or (n_tq >= n_par and n_par > 0) or (n_tq >= (n_arr * 0.30) and n_tq < n_par): estatus, razon = "✅ Normal", "Operación normal"
                elif n_tq < (n_arr * 0.30) and n_arr > 0: estatus, razon = "No arranca con su condición de tanque", "Nivel bajo"
                else: estatus, razon = "❌ Desconocida", "Estatus desconocido"

                st.toggle("Activar envío de alertas a Telegram", key="alertas_activas") # Botón de control 
                if inc == "Sin incidencia" and razon != "Operación normal" and (ahora_dt - fecha_bd) > timedelta(minutes=90):
                    if info['Pozos'] not in st.session_state.alertas_enviadas:
                        enviar_alerta(info['Pozos'], f"{n_tq:.2f}", f"{n_arr:.2f}", row['FECHA'].time(), h_p, h_a, razon)
                        st.session_state.alertas_enviadas[info['Pozos']] = ahora_dt
                
                lista_apg.append({
                    "Pozo": info['Pozos'], "Estatus_Paro": estatus, "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(), 
                    "Incidencia": inc, "Nivel_Tanque": f"{n_tq:.2f}" if n_tq > 0 else "Directo a red", 
                    "Nivel_Arranque": f"{n_arr:.2f}" if n_arr > 0 else "", "Nivel_Paro": f"{n_par:.2f}" if n_par > 0 else "", 
                    "V_L1": f"{float(v1):.2f}", "V_L2": f"{float(v2):.2f}", "V_L3": f"{float(v3):.2f}", "TS": row['FECHA']
                })
            else:
                if info['Pozos'] in st.session_state.alertas_enviadas: del st.session_state.alertas_enviadas[info['Pozos']]
                lista_enc.append({"Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time()})

        df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False) if lista_apg else pd.DataFrame()
        df_enc_full = pd.DataFrame(lista_enc).sort_values(by='Fecha', ascending=False) if lista_enc else pd.DataFrame()
        
        cols_ind = st.columns(4)
        with cols_ind[0]: render_card("Total Apagados", len(df_final), "#FFFFFF", "🔴")
        if not df_final.empty:
            with cols_ind[1]: render_card("Estatus Normal", len(df_final[df_final['Estatus_Paro'].str.contains('✅')]), "#00FF00", "✅")
            with cols_ind[2]: render_card("Por Incidencia", len(df_final[df_final['Estatus_Paro'].str.contains('⚠️')]), "#FFD700", "⚠️")
            with cols_ind[3]: render_card("Desconocida", len(df_final[df_final['Estatus_Paro'].str.contains('❌')]), "#FF0000", "❌")
        
        st.markdown("<hr>", unsafe_allow_html=True)
        col_izq, col_der = st.columns([0.65, 0.35])
        
        with col_izq:
            st.subheader("🔴 Pozos Apagados")
            if not df_final.empty:
                df_mostrar = df_final.drop(columns=['TS']).copy()
                df_mostrar['Fecha'] = df_mostrar['Fecha'].apply(lambda x: x.strftime('%d/%m/%y'))
                df_mostrar['Hora'] = df_mostrar['Hora'].apply(lambda x: x.strftime('%H:%M:%S'))
                
                def color_fila(row):
                    e = str(row['Estatus_Paro'])
                    c = '#FFD700' if '⚠️' in e else ('#00FF00' if '✅' in e else ('#FF0000' if '❌' in e else 'inherit'))
                    return [f'color: {c}'] * len(row)
                
                st.dataframe(
                    df_mostrar.style.apply(color_fila, axis=1)
                    .set_properties(**{'text-align': 'center'}, subset=['Nivel_Tanque', 'Nivel_Arranque', 'Nivel_Paro', 'V_L1', 'V_L2', 'V_L3']), 
                    use_container_width=True, hide_index=True
                )
        
        with col_der:
            st.subheader("🟢 Pozos Encendidos")
            if not df_enc_full.empty: st.dataframe(df_enc_full, use_container_width=True, hide_index=True)
                
           
        st.subheader("📋 Registro de Alertas")
        st.markdown(f'<div class="log-console">{"<br>".join(reversed(st.session_state.logs))}</div>', unsafe_allow_html=True)
    t.sleep(30)
