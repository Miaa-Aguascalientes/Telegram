import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import time, datetime, timedelta
import time as t
import threading
import requests
from zoneinfo import ZoneInfo

# Configuración de página
st.set_page_config(layout="wide", page_title="Consola de operación", page_icon="https://www.miaa.mx/favicon.ico")

# --- ESTADO DE SESIÓN ---
if 'alertas_enviadas' not in st.session_state: st.session_state.alertas_enviadas = {}
if 'logs' not in st.session_state: st.session_state.logs = []
if 'alertas_activas' not in st.session_state: st.session_state.alertas_activas = False
if 'busqueda_pozo' not in st.session_state: st.session_state.busqueda_pozo = ""
if 'user_to_delete' not in st.session_state: st.session_state.user_to_delete = None

zona_mx = ZoneInfo("America/Mexico_City")

# --- CONEXIÓN ROBUSTA Y RECONEXIÓN AUTOMÁTICA ---
@st.cache_resource
def get_engines(): 
    engine_dic = create_engine(
        st.secrets["databases"]["url_dic"],
        pool_pre_ping=True, pool_recycle=1800, pool_timeout=30
    )
    engine_scada = create_engine(
        st.secrets["databases"]["url_scada"],
        pool_pre_ping=True, pool_recycle=1800, pool_timeout=30
    )
    return engine_dic, engine_scada

ENGINE_DIC, ENGINE_SCADA = get_engines()

def obtener_datos(query, engine_tipo="dic", max_retries=3):
    """Ejecuta consultas con reintento automático ante desconexiones."""
    global ENGINE_DIC, ENGINE_SCADA
    engine = ENGINE_DIC if engine_tipo == "dic" else ENGINE_SCADA
    
    for intento in range(max_retries):
        try:
            return pd.read_sql(query, engine)
        except Exception as e:
            if intento < max_retries - 1:
                try:
                    engine.dispose()
                except:
                    pass
                ENGINE_DIC, ENGINE_SCADA = get_engines()
                engine = ENGINE_DIC if engine_tipo == "dic" else ENGINE_SCADA
                t.sleep(2)
            else:
                st.error(f"Error de conexión a la base de datos tras varios intentos: {e}")
                return pd.DataFrame()

def ejecutar_sql(query, params=None, max_retries=3):
    """Ejecuta sentencias SQL (INSERT/UPDATE/DELETE) con reconexión automática."""
    global ENGINE_DIC
    for intento in range(max_retries):
        try:
            with ENGINE_DIC.connect() as conn:
                with conn.begin():
                    conn.execute(text(query) if isinstance(query, str) else query, params or {})
            return True
        except Exception as e:
            if intento < max_retries - 1:
                try:
                    ENGINE_DIC.dispose()
                except:
                    pass
                _, ENGINE_SCADA = get_engines()
                t.sleep(2)
            else:
                raise e

# --- FUNCIONES ---
def es_periodo_de_paro_programado(t_par, t_arr):
    if t_par == time(0, 0) and t_arr == time(0, 0): return False
    ahora = datetime.now(zona_mx).time()
    if t_par < t_arr: return t_par <= ahora <= t_arr
    else: return ahora >= t_par or ahora <= t_arr

def es_hora_cercana_a_transicion(h_paro, h_arranque, margen_minutos=5):
    """Verifica si la hora actual está muy cerca del horario de paro o arranque programado."""
    ahora = datetime.now(zona_mx).time()
    ahora_dt = datetime.combine(datetime.today(), ahora)
    
    for h_prog in [h_paro, h_arranque]:
        if h_prog and h_prog != time(0, 0):
            prog_dt = datetime.combine(datetime.today(), h_prog)
            if abs((ahora_dt - prog_dt).total_seconds()) <= (margen_minutos * 60):
                return True
    return False

def registrar_cambio_estado():
    estado = "ACTIVADO" if st.session_state.alertas_activas else "DESACTIVADO"
    msg = f"[{datetime.now(zona_mx).strftime('%H:%M:%S')}] Servicio de alertas {estado}"
    st.session_state.logs.append(msg)

def enviar_alerta(pozo, nivel, nivel_arr, hora_alerta, h_paro, h_arranque, razon, hora_paro):
    token = st.secrets["telegram"]["token"]
    mensaje = f"📢 <b>Reporte Automatico Miaa</b>\n________________________________\n⚠️ <b>Alerta:</b> Bomba Apagada\n📍 <b>Pozo:</b> {pozo}\n⏳ <b>Hora del paro:</b> {hora_paro}\n💧 <b>Nivel Tanque:</b> {nivel} mts.\n↕️ <b>Nivel Arranque con TQ:</b> {nivel_arr} mts.\n⏲️ <b>Horario de Op:</b> {h_paro} - {h_arranque}\n🔍 <b>Motivo:</b> {razon}"
    def send():
        try:
            df_ids = obtener_datos("SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'", "dic")
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
    .logo-container img {
        width: 300px !important; 
        height: auto !important;
        display: block;
    }
</style>""", unsafe_allow_html=True)

def convertir_a_hora(valor):
    try: m = float(valor); return time(int((m // 60) % 24), int(m % 60))
    except: return time(0, 0)

# --- CABECERA ---
col_h1, col_h2 = st.columns([2, 9]) 
with col_h1:
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

# --- CARGA DE DATOS GENERALES ---
df_dic = obtener_datos("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", "dic")

try:
    df_destinatarios = obtener_datos("SELECT id, nombre, chart_id, activo, departamento FROM Diccionario_telegram", "dic")
except:
    df_destinatarios = pd.DataFrame()

st.divider()

# --- FRAGMENTO DE MONITOREO Y TABLAS DE POZOS (Actualización cada 1 minuto) ---
@st.fragment(run_every=60)
def monitor_pozos_fragment():
    col_izq, col_der = st.columns([0.80, 0.20])
    with col_izq:
        st.subheader("🔴 Pozos Apagados")
    with col_der:
        st.subheader("🟢 Pozos Encendidos")

    try:
        df_inc = obtener_datos("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", "scada")
        df_inc['KEY'] = df_inc['NUM_POZO'].astype(str).str.replace(r'[- ]', '', regex=True)
        mapa_inc = dict(zip(df_inc['KEY'], df_inc['DIAGNOSTICO_FALLA']))
    except: mapa_inc = {}

    tags = "', '".join(df_dic['bomba'].tolist())
    df = obtener_datos(f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", "scada")

    cols_corrientes = ['amperaje_L1', 'amperaje_L2', 'amperaje_L3']
    tags_aux_cols = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3'] + [c for c in cols_corrientes if c in df_dic.columns]

    tags_aux = list(set([str(t) for col in tags_aux_cols for t in df_dic[col].dropna().unique() if str(t).strip() != '']))

    df_h = pd.DataFrame()
    if tags_aux:
        lotes_aux = [tags_aux[i:i + 100] for i in range(0, len(tags_aux), 100)]
        lista_df_h = []
        for lote in lotes_aux:
            tags_str_lote = "', '".join(lote)
            df_lote = obtener_datos(f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str_lote}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)", "scada")
            if not df_lote.empty:
                lista_df_h.append(df_lote)
        if lista_df_h:
            df_h = pd.concat(lista_df_h, ignore_index=True)

    mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE'])) if not df_h.empty else {}

    lista_corrientes_encendidos = []
    tags_corr_list = []
    for _, d_row in df_dic.iterrows():
        for c_col in ['amperaje_L1', 'amperaje_L2', 'amperaje_L3']:
            if c_col in d_row and pd.notnull(d_row[c_col]) and str(d_row[c_col]).strip() != '':
                tags_corr_list.append(str(d_row[c_col]))

    mapa_actual_prom = {}
    tags_corr_unicos = list(set(tags_corr_list))
    if tags_corr_unicos:
        lotes_corr = [tags_corr_unicos[i:i + 100] for i in range(0, len(tags_corr_unicos), 100)]
        lista_df_act = []
        
        for lote in lotes_corr:
            tags_str_sql = "', '".join(lote)
            query_actual = f"""
                SELECT r.NAME, h.VALUE as VALOR_ACTUAL 
                FROM VfiTagNumHistory_Ultimo h 
                JOIN VfiTagRef r ON h.GATEID = r.GATEID 
                WHERE r.NAME IN ('{tags_str_sql}') 
                  AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)
            """
            df_act_lote = obtener_datos(query_actual, "scada")
            if not df_act_lote.empty:
                lista_df_act.append(df_act_lote)
        
        if lista_df_act:
            df_act_ultimos = pd.concat(lista_df_act, ignore_index=True)
            mapa_actual_prom = dict(zip(df_act_ultimos['NAME'].astype(str), df_act_ultimos['VALOR_ACTUAL']))

    lista_apg, lista_enc = [], []
    ahora_actual = datetime.now(zona_mx)

    for _, row in df.iterrows():
        df_match = df_dic[df_dic['bomba'] == row['NAME']]
        if df_match.empty: continue
        info = df_match.iloc[0]
        inc = mapa_inc.get(str(info['Pozos']).replace('-', '').replace(' ', ''), "Sin incidencia")
        n_tq, n_arr, n_par = float(mapa_aux.get(str(info.get('nivel_tanque', '')), 0) or 0), float(mapa_aux.get(str(info.get('nivel_arranque_tq', '')), 0) or 0), float(mapa_aux.get(str(info.get('nivel_paro_tq', '')), 0) or 0)
        h_p_val, h_a_val = convertir_a_hora(mapa_aux.get(str(info.get('H_paro', '')))), convertir_a_hora(mapa_aux.get(str(info.get('H_arranque', ''))))
        
        tag_l1 = str(info.get('amperaje_L1', ''))
        tag_l2 = str(info.get('amperaje_L2', ''))
        tag_l3 = str(info.get('amperaje_L3', ''))
        
        a1_val = float(mapa_actual_prom.get(tag_l1, 0) or 0) if tag_l1 else 0.0
        a2_val = float(mapa_actual_prom.get(tag_l2, 0) or 0) if tag_l2 else 0.0
        a3_val = float(mapa_actual_prom.get(tag_l3, 0) or 0) if tag_l3 else 0.0
        
        if a1_val > 0 or a2_val > 0 or a3_val > 0:
            prom_fases = (a1_val + a2_val + a3_val) / 3.0 if (a1_val + a2_val + a3_val) > 0 else 1.0
            desb_l1 = abs(a1_val - prom_fases) / prom_fases * 100 if prom_fases > 0 else 0.0
            desb_l2 = abs(a2_val - prom_fases) / prom_fases * 100 if prom_fases > 0 else 0.0
            desb_l3 = abs(a3_val - prom_fases) / prom_fases * 100 if prom_fases > 0 else 0.0
            max_desb = max(desb_l1, desb_l2, desb_l3)
            
            if row['VALUE'] != 0:
                lista_corrientes_encendidos.append({
                    "Pozo": info['Pozos'],
                    "A1 (Act)": f"{a1_val:.2f} A",
                    "A2 (Act)": f"{a2_val:.2f} A",
                    "A3 (Act)": f"{a3_val:.2f} A",
                    "Desb. Max (%)": f"{max_desb:.2f}%",
                    "val_num_desb": max_desb,
                    "Fecha": row['FECHA'].date(),
                    "Hora": row['FECHA'].time()
                })

        fecha_bd = row['FECHA']
        if pd.notnull(fecha_bd):
            if fecha_bd.tzinfo is None:
                fecha_bd = fecha_bd.tz_localize(None).replace(tzinfo=zona_mx)
            else:
                fecha_bd = fecha_bd.astimezone(zona_mx)
        
        if row['VALUE'] == 0:
            umbral_alerta = n_arr * 0.70
            if inc != "Sin incidencia": 
                estatus, razon = "⚠️ Parado por incidencia", inc
            elif es_periodo_de_paro_programado(h_p_val, h_a_val) or (n_tq >= n_par and n_par > 0) or (n_tq >= umbral_alerta and n_tq < n_par): 
                estatus, razon = "✅ Normal", "Operación normal"
            elif n_tq < umbral_alerta and n_arr > 0: 
                estatus, razon = "❌ No arranca con su condición de tanque", "No arranca con su condicion de nivel bajo de tanque"
            else: 
                estatus, razon = "❌ Estatus desconocido", "Estatus desconocido"
            
            # Validación para evitar enviar alerta si el pozo está en su ventana de arranque/paro programado
            en_transicion_horario = es_hora_cercana_a_transicion(h_p_val, h_a_val, margen_minutos=10)

            if (st.session_state.alertas_activas and 
                not en_transicion_horario and 
                fecha_bd.date() == ahora_actual.date() and 
                (ahora_actual - fecha_bd) >= timedelta(hours=3.5) and 
                inc == "Sin incidencia" and 
                razon != "Operación normal" and 
                info['Pozos'] not in st.session_state.alertas_enviadas):
                
                enviar_alerta(info['Pozos'], f"{n_tq:.2f}", f"{n_arr:.2f}", row['FECHA'].time(), h_p_val, h_a_val, razon, row['FECHA'].time().strftime('%H:%M:%S'))
                st.session_state.alertas_enviadas[info['Pozos']] = ahora_actual
            
            lista_apg.append({"Pozo": info['Pozos'], "Estatus_Paro": estatus, "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(), "H_Paro": h_p_val, "H_Arranque": h_a_val, "Incidencia": inc, "Nivel_Tanque": f"{n_tq:.2f}" if n_tq > 0 else "Directo a red", "Nivel_Arranque": f"{n_arr:.2f}" if n_arr > 0 else "", "Nivel_Paro": f"{n_par:.2f}" if n_par > 0 else "", "V_L1": f"{float(mapa_aux.get(str(info.get('voltaje_L1','')), 0)):.2f}", "V_L2": f"{float(mapa_aux.get(str(info.get('voltaje_L2','')), 0)):.2f}", "V_L3": f"{float(mapa_aux.get(str(info.get('voltaje_L3','')), 0)):.2f}", "TS": row['FECHA']})
        else:
            if info['Pozos'] in st.session_state.alertas_enviadas: del st.session_state.alertas_enviadas[info['Pozos']]
            lista_enc.append({"Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(), "TS": row['FECHA']})

    df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False) if lista_apg else pd.DataFrame()
    df_enc_full = pd.DataFrame(lista_enc).sort_values(by='TS', ascending=False) if lista_enc else pd.DataFrame()
    
    # ORDENAMIENTO DE AMPERAJES: Mayor a menor usando la columna numérica interna de desbalance
    df_enc_amps = pd.DataFrame(lista_corrientes_encendidos)
    if not df_enc_amps.empty:
        df_enc_amps = df_enc_amps.sort_values(by='val_num_desb', ascending=False).drop(columns=['val_num_desb'])
    else:
        df_enc_amps = pd.DataFrame()

    with col_izq:
        if not df_final.empty:
            def color_fila(row):
                e = str(row['Estatus_Paro'])
                c = '#FF0000' if '❌' in e else '#FFD700' if '⚠️' in e else '#00FF00' if '✅' in e else 'inherit'
                return [f'color: {c}'] * len(row)
            st.dataframe(df_final.drop(columns=['TS']).style.apply(color_fila, axis=1).set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
        else:
            st.info("No hay pozos apagados registrados.")

    with col_der:
        df_mostrar = df_enc_full
        if st.session_state.busqueda_pozo:
            df_mostrar = df_enc_full[df_enc_full['Pozo'].astype(str).str.contains(st.session_state.busqueda_pozo, case=False, na=False)]
        if not df_mostrar.empty: 
            st.dataframe(df_mostrar.drop(columns=['TS']), use_container_width=True, hide_index=True)
        else:
            st.info("No hay pozos encendidos registrados.")

    st.subheader("📊 Pozos Encendidos y sus Amperajes (Último Valor Registrado)")
    df_mostrar_amps = df_enc_amps
    if st.session_state.busqueda_pozo and not df_enc_amps.empty:
        df_mostrar_amps = df_enc_amps[df_enc_amps['Pozo'].astype(str).str.contains(st.session_state.busqueda_pozo, case=False, na=False)]
    
    if not df_mostrar_amps.empty:
        def color_fila_amperajes(df_subset):
            """Pinta los primeros 5 en rojo, los siguientes 10 en amarillo y el resto en verde."""
            estilos = []
            for i in range(len(df_subset)):
                if i < 5:
                    c = '#FF0000'  # 5 más graves (Rojo)
                elif i < 15:
                    c = '#FFD700'  # 10 medio graves (Amarillo)
                else:
                    c = '#00FF00'  # Demás (Verde)
                estilos.append([f'color: {c}'] * len(df_subset.columns))
            return pd.DataFrame(estilos, index=df_subset.index, columns=df_subset.columns)

        st.dataframe(df_mostrar_amps.style.apply(color_fila_amperajes, axis=None).set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
    else:
        st.info("No hay datos de corriente disponibles para los pozos encendidos.")
        
    st.subheader("📋 Registro de Alertas")
    st.markdown(f'<div class="log-console">{"<br>".join(reversed(st.session_state.logs))}</div>', unsafe_allow_html=True)

monitor_pozos_fragment()

st.divider()

# --- GESTIÓN DE DESTINATARIOS ---
st.subheader("👥 Gestión de Destinatarios de Alertas (Telegram)")

with st.expander("➕ Añadir nuevo destinatario"):
    with st.form("form_nuevo_usuario_dinamico_unico"):
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            nuevo_nombre = st.text_input("Nombre completo", key="input_nuevo_nombre")
        with f_col2:
            nuevo_chart = st.text_input("Chart ID (Telegram)", key="input_nuevo_chart")
        with f_col3:
            nuevo_depto = st.text_input("Departamento", value="Planeacion Tecnica", key="input_nuevo_depto")
        
        btn_crear = st.form_submit_button("Guardar Usuario")
        if btn_crear:
            if nuevo_nombre and nuevo_chart:
                try:
                    df_max_id = obtener_datos("SELECT MAX(CAST(id AS UNSIGNED)) as max_id FROM Diccionario_telegram", "dic")
                    siguiente_id = 1
                    if not df_max_id.empty and pd.notnull(df_max_id.iloc[0]['max_id']):
                        siguiente_id = int(df_max_id.iloc[0]['max_id']) + 1
                    
                    nuevo_id_str = f"{siguiente_id:03d}"

                    ejecutar_sql(
                        "INSERT INTO Diccionario_telegram (id, nombre, chart_id, activo, departamento) VALUES (:id, :nombre, :chart_id, 'Si', :depto)",
                        {"id": nuevo_id_str, "nombre": nuevo_nombre, "chart_id": nuevo_chart, "depto": nuevo_depto}
                    )
                    st.success(f"Usuario {nuevo_nombre} añadido correctamente con ID {nuevo_id_str}.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error al insertar el usuario: {ex}")
            else:
                st.warning("Por favor completa los campos obligatorios (Nombre y Chart ID).")

if not df_destinatarios.empty:
    for idx, row_user in df_destinatarios.iterrows():
        cols_u = st.columns([2, 2, 2, 1, 1])
        with cols_u[0]:
            st.text(f"👤 {row_user['nombre']}")
        with cols_u[1]:
            st.text(f"💬 ID: {row_user['chart_id']}")
        with cols_u[2]:
            st.text(f"🏢 {row_user['departamento']}")
        with cols_u[3]:
            actual_val = True if str(row_user['activo']).strip().lower() == 'si' else False
            nuevo_estado = st.toggle("Activo", value=actual_val, key=f"toggle_user_{row_user['id']}_{idx}")
            nuevo_str = "Si" if nuevo_estado else "No"
            if nuevo_str != str(row_user['activo']):
                try:
                    ejecutar_sql("UPDATE Diccionario_telegram SET activo = :val WHERE id = :uid", {"val": nuevo_str, "uid": row_user['id']})
                    st.toast(f"Actualizado: {row_user['nombre']} -> {nuevo_str}")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error al actualizar: {ex}")
        with cols_u[4]:
            if st.button("🗑️ Eliminar", key=f"del_user_{row_user['id']}_{idx}"):
                st.session_state.user_to_delete = row_user['id']
                st.rerun()
else:
    st.info("No se encontraron registros en Diccionario_telegram.")

if st.session_state.user_to_delete is not None:
    uid_Target = st.session_state.user_to_delete
    st.warning(f"⚠️ Estás a punto de eliminar al usuario con ID: {uid_Target}. Esta acción no se puede deshacer.")
    
    confirm_text = st.text_input("Para confirmar, escribe la palabra requerida en el siguiente campo:", key="input_confirm_delete")
    
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("Sí, confirmar eliminación", type="primary", key="btn_ejecutar_eliminar_def"):
            if confirm_text.strip().lower() == "delete":
                try:
                    ejecutar_sql("DELETE FROM Diccionario_telegram WHERE id = :uid", {"uid": uid_Target})
                    st.success("Registro eliminado correctamente.")
                    st.session_state.user_to_delete = None
                    t.sleep(0.5)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error al eliminar de la base de datos: {ex}")
            else:
                st.error("La palabra ingresada no coincide. Inténtalo de nuevo.")
    with c_btn2:
        if st.button("Cancelar", key="btn_cancelar_eliminar_def"):
            st.session_state.user_to_delete = None
            st.rerun()
