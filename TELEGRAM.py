import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import requests
from datetime import datetime, timedelta, time
import locale

# Intentar establecer el idioma en español para fechas
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass 

# --- CONFIGURACIÓN DE PÁGINA STREAMLIT ---
st.set_page_config(layout="wide", page_title="Sistema de monitoreo", page_icon="https://www.miaa.mx/favicon.ico")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        h1, h2, h3 {
            color: #ffffff;
        }
    </style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DE CONEXIÓN ROBUSTA ---
ENGINE_DIC = create_engine(
    "mysql+pymysql://miaamx_telemetria2:bWkrw1Uum1O&@miaa.mx/miaamx_telemetria2",
    pool_pre_ping=True, pool_recycle=1800, pool_timeout=30
)
ENGINE_SCADA = create_engine(
    "mysql+pymysql://miaamx_dashboard:h97_p,NQPo=l@miaa.mx/miaamx_telemetria",
    pool_pre_ping=True, pool_recycle=1800, pool_timeout=30
)
TOKEN = '8985322491:AAF1QviZ0h0I4EVC_LFGeOZk51b4l0VaSq4'

if 'alertas_enviadas' not in st.session_state:
    st.session_state.alertas_enviadas = {}

def convertir_a_hora(valor):
    try:
        m = float(valor)
        return time(int((m // 60) % 24), int(m % 60))
    except: 
        return time(0, 0)

def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): 
        return False
    ahora = datetime.now().time()
    if t_par < t_arr:
        return t_par <= ahora <= t_arr
    else:
        return ahora >= t_par or ahora <= t_arr

def enviar_alerta(pozo, nivel, nivel_arr, fecha, hora, h_paro, h_arranque, razon):
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
    try:
        query = "SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'"
        df_ids = pd.read_sql(query, ENGINE_DIC)
        lista_ids = df_ids['chart_id'].tolist()
        for chat_id in lista_ids:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
            except: 
                continue
    except: 
        pass

def obtener_datos(query, engine):
    try: 
        return pd.read_sql(query, engine)
    except Exception: 
        engine.dispose()
        return pd.read_sql(query, engine)

# --- CABECERA Y LOGOTIPO ---
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    st.image("https://www.miaa.mx/favicon.ico", width=60)
with col_titulo:
    st.markdown("<h2 style='text-align: left; color: #ffffff;'>Sistema de Monitoreo MIAA 24/7</h2>", unsafe_allow_html=True)

st.markdown("---")

try:
    # 1. Cargar diccionario de pozos con voltajes
    query_dic = "SELECT Pozos, bomba, H_arranque, H_paro, nivel_tanque, nivel_arranque_tq, nivel_paro_tq, voltaje_L1, voltaje_L2, voltaje_L3 FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'"
    df_dic = obtener_datos(query_dic, ENGINE_DIC)
    tags_str = "', '".join(df_dic['bomba'].tolist())
    
    # 2. Cargar incidencias desde SCADA
    df_inc = obtener_datos("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
    df_inc['P_LIMPIO'] = df_inc['NUM_POZO'].str.replace('-', '', regex=False)
    mapa_inc = dict(zip(df_inc['P_LIMPIO'], df_inc['DIAGNOSTICO_FALLA']))

    # 3. Obtener estados de las bombas ordenados por fecha y hora más recientes
    query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
    df = obtener_datos(query, ENGINE_SCADA).sort_values(by='FECHA', ascending=False)
    
    # Recolectar tags auxiliares
    lista_tags_aux = list(set(
        df_dic['H_arranque'].tolist() + 
        df_dic['H_paro'].tolist() + 
        df_dic['nivel_tanque'].dropna().tolist() + 
        df_dic['nivel_arranque_tq'].dropna().tolist() + 
        df_dic['nivel_paro_tq'].dropna().tolist() +
        df_dic['voltaje_L1'].dropna().tolist() +
        df_dic['voltaje_L2'].dropna().tolist() +
        df_dic['voltaje_L3'].dropna().tolist()
    ))
    
    all_aux_tags = "', '".join(lista_tags_aux)
    
    df_h = obtener_datos(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{all_aux_tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", ENGINE_SCADA)
    mapa_aux = dict(zip(df_h['NAME'], df_h['VALUE']))

    lista_apg = []
    lista_enc = []
    enc, apg, ahora_dt = 0, 0, datetime.now()
    
    for _, row in df.iterrows():
        info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
        pozo = info['Pozos']
        
        v1 = mapa_aux.get(info['voltaje_L1'], 0)
        v2 = mapa_aux.get(info['voltaje_L2'], 0)
        v3 = mapa_aux.get(info['voltaje_L3'], 0)
        
        v1 = f"{float(v1):.1f}"
        v2 = f"{float(v2):.1f}"
        v3 = f"{float(v3):.1f}"
        
        inc = mapa_inc.get(pozo.replace('-', ''), "Sin incidencia")
        f = row['FECHA'].strftime('%d de %B de %Y')
        h = row['FECHA'].strftime('%H:%M:%S')
        
        t_arr = convertir_a_hora(mapa_aux.get(info['H_arranque'], 0))
        t_par = convertir_a_hora(mapa_aux.get(info['H_paro'], 0))
        
        nivel_act = mapa_aux.get(info['nivel_tanque'])
        niv_arr = mapa_aux.get(info['nivel_arranque_tq'])
        nivel_act_str = f"{float(nivel_act):.2f}" if nivel_act is not None else "Directo a Red"
        niv_arr_str = f"{float(niv_arr):.2f}" if niv_arr is not None else ""
        niv_par_str = f"{float(mapa_aux.get(info['nivel_paro_tq'])):.2f}" if mapa_aux.get(info['nivel_paro_tq']) is not None else ""
        
        if row['VALUE'] == 0:
            apg += 1
            es_paro_programado = es_periodo_de_paro_programado(t_par, t_arr)
            
            nivel_val = float(nivel_act) if nivel_act is not None else 0
            niv_arr_val = float(niv_arr) if niv_arr is not None else 0
            niv_par_val = float(mapa_aux.get(info['nivel_paro_tq'], 0)) if mapa_aux.get(info['nivel_paro_tq']) is not None else 0
            
            umbral_inferior = niv_arr_val * 0.30
            
            es_paro_por_nivel_bajo = (nivel_val < umbral_inferior and niv_arr_val > 0)
            es_paro_por_nivel_alto = (nivel_val >= niv_par_val and niv_par_val > 0)
            es_normal_por_nivel = (nivel_val >= umbral_inferior and nivel_val < niv_par_val)
            
            if inc.lower().strip() != "sin incidencia":
                estatus_paro = "⚠️ Parado por incidencia"
                razon_alerta = inc
            elif es_paro_programado or es_paro_por_nivel_alto or es_normal_por_nivel:
                estatus_paro = "✅ Normal"
                razon_alerta = "Operación normal"
            elif es_paro_por_nivel_bajo:
                estatus_paro = "No arranca con su condición de tanque"
                razon_alerta = "No arranca con su condición de tanque"
            else:
                estatus_paro = "❌ Desconocida"
                razon_alerta = "Estatus desconocido"
            
            lista_apg.append({
                "Pozo": pozo, "Fecha": f, "Hora": h, "Incidencia": inc,
                "H_paro": t_par.strftime('%H:%M'), "H_arranque": t_arr.strftime('%H:%M'),
                "Nivel": nivel_act_str, "Niv_Arr": niv_arr_str, "Niv_Par": niv_par_str,
                "Estatus_Paro": estatus_paro, "V_L1": v1, "V_L2": v2, "V_L3": v3
            })
            
            es_hoy = row['FECHA'].date() == ahora_dt.date()
            if es_hoy and inc.lower().strip() == "sin incidencia" and razon_alerta != "Operación normal":
                if es_paro_por_nivel_bajo or estatus_paro == "❌ Desconocida":
                    if pozo not in st.session_state.alertas_enviadas:
                        if (ahora_dt - row['FECHA']) > timedelta(minutes=90):
                            enviar_alerta(pozo, nivel_act_str, niv_arr_str, f, h, t_par.strftime('%H:%M'), t_arr.strftime('%H:%M'), razon_alerta)
                            st.session_state.alertas_enviadas[pozo] = ahora_dt
        else:
            enc += 1
            lista_enc.append({
                "Pozo": pozo, "Fecha": f, "Hora": h,
                "H_paro": t_par.strftime('%H:%M'), "H_arranque": t_arr.strftime('%H:%M'),
                "Nivel": nivel_act_str, "Niv_Arr": niv_arr_str, "Niv_Par": niv_par_str,
                "V_L1": v1, "V_L2": v2, "V_L3": v3
            })
            if pozo in st.session_state.alertas_enviadas: 
                del st.session_state.alertas_enviadas[pozo]

    # --- MÉTRICAS SUPERIORES ---
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown(f"<h3 style='color: #f44336; text-align: center;'>Apagados: {apg}</h3>", unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"<h3 style='color: #4caf50; text-align: center;'>Encendidos: {enc}</h3>", unsafe_allow_html=True)

    st.markdown("---")

    # --- RENDERIZADO DE TABLAS ---
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown("<h4 style='text-align: center;'>APAGADOS (Atención)</h4>", unsafe_allow_html=True)
        if lista_apg:
            df_apg = pd.DataFrame(lista_apg)
            def color_estatus(val):
                if "Parado por incidencia" in str(val):
                    return 'color: #FFD700; font-weight: bold;'
                elif "Normal" in str(val):
                    return 'color: #32CD32; font-weight: bold;'
                else:
                    return 'color: #FF4500; font-weight: bold;'
            
            st.dataframe(df_apg.style.applymap(color_estatus, subset=['Estatus_Paro']), use_container_width=True, hide_index=True)
        else:
            st.info("No hay pozos apagados registrados.")

    with col_t2:
        st.markdown("<h4 style='text-align: center;'>ENCENDIDOS</h4>", unsafe_allow_html=True)
        if lista_enc:
            df_enc = pd.DataFrame(lista_enc)
            st.dataframe(df_enc, use_container_width=True, hide_index=True)
        else:
            st.info("No hay pozos encendidos registrados.")

except Exception as e:
    st.error(f"Error en la ejecución del dashboard: {e}")
