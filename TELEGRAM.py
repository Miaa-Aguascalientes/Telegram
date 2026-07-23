import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time, datetime, timedelta
import time as t
import threading
import requests
from zoneinfo import ZoneInfo
from sqlalchemy.exc import SQLAlchemyError

# Configuración de página
st.set_page_config(layout="wide", page_title="Consola de operacón", page_icon="https://www.miaa.mx/favicon.ico")

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

def registrar_cambio_estado():
    estado = "ACTIVADO" if st.session_state.alertas_activas else "DESACTIVADO"
    msg = f"[{datetime.now(zona_mx).strftime('%H:%M:%S')}] Servicio de alertas {estado}"
    st.session_state.logs.append(msg)

def enviar_alerta(pozo, nivel, nivel_arr, hora_alerta, h_paro, h_arranque, razon, hora_paro):
    token = st.secrets["telegram"]["token"]
    mensaje = f"📢 <b>Reporte Automatico Miaa</b>\n________________________________\n⚠️ <b>Alerta:</b> Bomba Apagada\n📍 <b>Pozo:</b> {pozo}\n⏳ <b>Hora del paro:</b> {hora_paro}\n💧 <b>Nivel Tanque:</b> {nivel} mts.\n↕️ <b>Nivel Arranque con TQ:</b> {nivel_arr} mts.\n⏲️ <b>Horario de Op:</b> {h_paro} - {h_arranque}\n🔍 <b>Motivo:</b> {razon}"
    def send():
        try:
            engine_dic_bg = create_engine(
                st.secrets["databases"]["url_dic"], 
                pool_pre_ping=True, 
                pool_recycle=300,
                connect_args={"connect_timeout": 10}
            )
            with engine_dic_bg.connect() as conn:
                df_ids = pd.read_sql("SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'", conn)
            for chat_id in df_ids['chart_id'].tolist(): 
                requests.get(f"https://api.telegram.org/bot{token}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
        except: pass
    threading.Thread(target=send, daemon=True).start()
    st.session_state.logs.append(f"[{datetime.now(zona_mx).strftime('%H:%M:%S')}] Alerta enviada: {pozo} - {razon} (Paro: {hora_paro})")

# --- CSS ---
st.write("""<style>
    #MainMenu, header {visibility: hidden;} 
    .block-container {padding-top: 0rem !important; padding-bottom: 0rem !important;} 
    .custom-title {color: #00E5FF !important; font-size: 2rem; font-weight: bold; margin-bottom: 0px; text-align: center; margin-top: 0px;} 
    .log-console {background-color: #0e1117; color: #00FF00; font-family: monospace; padding: 10px; border: 1px solid #003366; border-radius: 5px; height: 150px; overflow-y: scroll; font-size: 0.85rem;}
    
    /* Esta es la regla que forzará el tamaño del logo */
    .logo-container img {
        width: 300px !important; 
        height: auto !important;
        display: block;
    }
</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_engines(): 
    return (
        create_engine(st.secrets["databases"]["url_dic"], pool_pre_ping=True, pool_recycle=300, connect_args={"connect_timeout": 15}), 
        create_engine(st.secrets["databases"]["url_scada"], pool_pre_ping=True, pool_recycle=300, connect_args={"connect_timeout": 15})
    )

ENGINE_DIC, ENGINE_SCADA = get_engines()

def convertir_a_hora(valor):
    try: m = float(valor); return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

# --- CABECERA ---
col_h1, col_h2 = st.columns([2, 9]) # Le damos más espacio a la columna del logo
with col_h1:
    # Fuerza máxima: usamos un contenedor que impone el tamaño sí o sí
    st.markdown("""
        <div style="width: 250px;">
            <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" 
                 style="width: 100%; height: auto; display: block;">
        </div>
    """, unsafe_allow_html=True)

with col_h2: 
    st.markdown('<h1 class="custom-title">Consola de operación</h1>', unsafe_allow_html=True)
st.divider()

# --- FILA ALINEADA: TOGGLE Y BUSCADOR ---
c1, c2, c3 = st.columns([0.3, 0.3, 0.4]) 
with c1:
    st.write("###")
    st.toggle("Activar envío de alertas a Telegram", key="alertas_activas", on_change=registrar_cambio_estado) 
with c3:
    st.text_input("🔍 Buscar pozo (solo encendidos)...", key='busqueda_pozo')

# --- ESTRUCTURA ---
col_izq, col_der = st.columns([0.65, 0.35])
with col_izq:
    st.subheader("🔴 Pozos Apagados")
    placeholder_apg = st.empty()
with col_der:
    st.subheader("🟢 Pozos Encendidos")
    placeholder_enc = st.empty()

placeholder_logs = st.empty()

# --- BUCLE ---
while True:
    try:
        with ENGINE_DIC.connect() as conn_dic, ENGINE_SCADA.connect() as conn_scada:
            df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", conn_dic)
            
            try:
                df_inc = pd.read_sql("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", conn_scada)
                df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
                mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
            except: mapa_inc = {}

            tags = "', '".join(df_dic['bomba'].tolist())
            df = pd.read_sql(f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", conn_scada)
            tags_aux = [str(t) for col in ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3'] for t in df_dic[col].dropna().unique()]
            df_h = pd.read_sql(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", conn_scada)
            mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

        lista_apg, lista_enc = [], []
        ahora_actual = datetime.now(zona_mx)

        for _, row in df.iterrows():
            df_match = df_dic[df_dic['bomba'] == row['NAME']]
            if df_match.empty: continue
            info = df_match.iloc[0]
            inc = mapa_inc.get(str(info['Pozos']).replace('-', '').replace(' ', ''), "Sin incidencia")
            n_tq, n_arr, n_par = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0), float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0), float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)
            h_p_val, h_a_val = convertir_a_hora(mapa_aux.get(str(info['H_paro']))), convertir_a_hora(mapa_aux.get(str(info['H_arranque'])))
            fecha_bd = row['FECHA'].tz_localize(None).replace(tzinfo=zona_mx) if row['FECHA'].tzinfo is None else row['FECHA'].astimezone(zona_mx)
            
            if row['VALUE'] == 0:
                umbral_alerta = n_arr * 0.50
                if inc != "Sin incidencia": estatus, razon = "⚠️ Parado por incidencia", inc
                elif es_periodo_de_paro_programado(h_p_val, h_a_val) or (n_tq >= n_par and n_par > 0) or (n_tq >= umbral_alerta and n_tq < n_par): estatus, razon = "✅ Normal", "Operación normal"
                elif n_tq < umbral_alerta and n_arr > 0: estatus, razon = "❌ No arranca con su condición de tanque", "Nivel bajo"
                else: estatus, razon = "❌ Estatus desconocido", "Estatus desconocido"
                
                if (st.session_state.alertas_activas and fecha_bd.date() == ahora_actual.date() and (ahora_actual - fecha_bd) >= timedelta(hours=3) and inc == "Sin incidencia" and razon != "Operación normal" and info['Pozos'] not in st.session_state.alertas_enviadas):
                    enviar_alerta(info['Pozos'], f"{n_tq:.2f}", f"{n_arr:.2f}", row['FECHA'].time(), h_p_val, h_a_val, razon, row['FECHA'].time().strftime('%H:%M:%S'))
                    st.session_state.alertas_enviadas[info['Pozos']] = ahora_actual
                
                lista_apg.append({
                    "Pozo": info['Pozos'], 
                    "Estatus_Paro": estatus, 
                    "Fecha": row['FECHA'].date(), 
                    "Hora": row['FECHA'].strftime('%H:%M'), 
                    "H_Paro": h_p_val.strftime('%H:%M'), 
                    "H_Arranque": h_a_val.strftime('%H:%M'), 
                    "Incidencia": inc, 
                    "Nivel_Tanque": f"{n_tq:.2f}" if n_tq > 0 else "Directo a red", 
                    "Nivel_Arranque": f"{n_arr:.2f}" if n_arr > 0 else "", 
                    "Nivel_Paro": f"{n_par:.2f}" if n_par > 0 else "", 
                    "V_L1": f"{float(mapa_aux.get(str(info['voltaje_L1']), 0)):.2f}", 
                    "V_L2": f"{float(mapa_aux.get(str(info['voltaje_L2']), 0)):.2f}", 
                    "V_L3": f"{float(mapa_aux.get(str(info['voltaje_L3']), 0)):.2f}", 
                    "TS": row['FECHA']
                })
            else:
                if info['Pozos'] in st.session_state.alertas_enviadas: del st.session_state.alertas_enviadas[info['Pozos']]
                lista_enc.append({
                    "Pozo": info['Pozos'], 
                    "Fecha": row['FECHA'].date(), 
                    "Hora": row['FECHA'].strftime('%H:%M'), 
                    "TS": row['FECHA']
                })

        df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False) if lista_apg else pd.DataFrame()
        df_enc_full = pd.DataFrame(lista_enc).sort_values(by='TS', ascending=False) if lista_enc else pd.DataFrame()
        
        with placeholder_apg:
            if not df_final.empty:
                def color_fila(row):
                    e = str(row['Estatus_Paro'])
                    c = '#FF0000' if '❌' in e else '#FFD700' if '⚠️' in e else '#00FF00' if '✅' in e else 'inherit'
                    return [f'color: {c}'] * len(row)
                st.dataframe(df_final.drop(columns=['TS']).style.apply(color_fila, axis=1).set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
        
        with placeholder_enc:
            df_mostrar = df_enc_full
            if st.session_state.busqueda_pozo:
                df_mostrar = df_enc_full[df_enc_full['Pozo'].astype(str).str.contains(st.session_state.busqueda_pozo, case=False, na=False)]
            if not df_mostrar.empty: 
                st.dataframe(df_mostrar.drop(columns=['TS']), use_container_width=True, hide_index=True)
                
    except SQLAlchemyError as e:
        st.error(f"Error de conexión con la base de datos (Timed Out / No se pudo alcanzar el servidor): {e}")
    except Exception as e:
        st.error(f"Ocurrió un error inesperado: {e}")
        
    with placeholder_logs:
        st.subheader("📋 Registro de Alertas")
        st.markdown(f'<div class="log-console">{"<br>".join(reversed(st.session_state.logs))}</div>', unsafe_allow_html=True)
    
    t.sleep(30)
