import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import time
import time as t

st.set_page_config(layout="wide", page_title="Sistema de monitoreo", page_icon="https://www.miaa.mx/favicon.ico")

# --- CSS DE DISEÑO ---
st.write("""
<style>
    #MainMenu, header {visibility: hidden;}
    .block-container {padding-top: 0.2rem !important; padding-bottom: 0rem !important;}
    .custom-title {color: #00E5FF !important; font-size: 2rem; font-weight: bold; margin-bottom: 5px; text-align: center;}
    
    .dashboard-card {
        background: linear-gradient(135deg, #1e2630 0%, #0e1117 100%);
        border: 2px solid #003366; 
        border-radius: 8px; 
        padding: 4px 8px !important; 
        text-align: center; 
        margin: 2px !important;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .card-label {color: #ffffff; font-size: 0.85rem !important; font-weight: 500; margin: 0 !important;}
    .card-value {font-size: 1rem !important; font-weight: bold; margin-left: 10px;}
</style>
""", unsafe_allow_html=True)

def render_card(label, value, color_val, icon):
    st.write(f"""
        <div class="dashboard-card">
            <div class="card-label">{icon} {label}</div>
            <div class="card-value" style="color: {color_val}">{value}</div>
        </div>
    """, unsafe_allow_html=True)

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

# Cabecera
col_h1, col_h2 = st.columns([1, 10])
with col_h1:
    st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=150)
with col_h2:
    st.markdown('<h1 class="custom-title">Sistema de Monitoreo</h1>', unsafe_allow_html=True)

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

        def format_nivel(v):
            try:
                valor = float(v)
                return "Directo a red" if valor <= 0 else f"{valor:.2f}"
            except (ValueError, TypeError): return "Directo a red"

        def format_param(v):
            try:
                valor = float(v)
                return f"{valor:.2f}" if valor > 0 else ""
            except (ValueError, TypeError): return ""

        for _, row in df.iterrows():
            df_match = df_dic[df_dic['bomba'] == row['NAME']]
            if df_match.empty: continue
            info = df_match.iloc[0]
            
            pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
            inc = mapa_inc.get(pozo_key, "Sin incidencia")
            
            data_row = {
                "Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(),
                "Incidencia": inc, "H_paro": convertir_a_hora(mapa_aux.get(str(info['H_paro']))), 
                "H_arranque": convertir_a_hora(mapa_aux.get(str(info['H_arranque']))),
                "Nivel": format_nivel(mapa_aux.get(str(info['nivel_tanque']), 0)),
                "Niv_Arr": format_param(mapa_aux.get(str(info['nivel_arranque_tq']), 0)),
                "Niv_Par": format_param(mapa_aux.get(str(info['nivel_paro_tq']), 0)),
                "V_L1": int(float(mapa_aux.get(str(info['voltaje_L1']), 0) or 0)), 
                "V_L2": int(float(mapa_aux.get(str(info['voltaje_L2']), 0) or 0)), 
                "V_L3": int(float(mapa_aux.get(str(info['voltaje_L3']), 0) or 0)),
                "TS": row['FECHA']
            }

            if row['VALUE'] == 0:
                estatus = "⚠️ Parado por incidencia" if inc != "Sin incidencia" else ("✅ Normal" if (float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0) > 0) else "❌ Desconocida")
                data_row["Estatus_Paro"] = estatus
                lista_apg.append(data_row)
            else:
                lista_enc.append(data_row)

        df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False).reset_index(drop=True) if lista_apg else pd.DataFrame()
        df_enc_full = pd.DataFrame(lista_enc).sort_values(by='TS', ascending=False).reset_index(drop=True) if lista_enc else pd.DataFrame()
        
        cols_ind = st.columns(4)
        with cols_ind[0]: render_card("Total Apagados", len(df_final), "#FFFFFF", "🔴")
        if not df_final.empty:
            with cols_ind[1]: render_card("Estatus Normal", len(df_final[df_final['Estatus_Paro'].str.contains('✅', na=False)]), "#00FF00", "✅")
            with cols_ind[2]: render_card("Por Incidencia", len(df_final[df_final['Estatus_Paro'].str.contains('⚠️', na=False)]), "#FFD700", "⚠️")
            with cols_ind[3]: render_card("Desconocida", len(df_final[df_final['Estatus_Paro'].str.contains('❌', na=False)]), "#FF0000", "❌")
        else:
            for c in cols_ind[1:]:
                with c: render_card("-", 0, "#888888", "⚪")
        
        st.markdown("<hr style='margin: 10px 0; border: 1px solid #00E5FF;'>", unsafe_allow_html=True)
        
        # --- FUNCIÓN ESTILO CON COLOR Y CENTRADO ---
        def estilo_total(row):
            # Obtenemos el color base según el estatus
            e = str(row.get('Estatus_Paro', ''))
            c = '#FFD700' if '⚠️' in e else ('#00FF00' if '✅' in e else ('#FF0000' if '❌' in e else 'white'))
            
            estilos = [f'color: {c}; text-align: left;'] * len(row)
            
            for i, col in enumerate(row.index):
                # Aplicamos centrado a los voltajes sin sobreescribir el color
                if col in ['V_L1', 'V_L2', 'V_L3']:
                    estilos[i] = f'color: {c}; text-align: center !important;'
            return estilos
        
        col_izq, col_der = st.columns([0.65, 0.35])
        
        with col_izq:
            st.subheader("🔴 Pozos Apagados")
            if not df_final.empty:
                cols_orden = ["Pozo", "Estatus_Paro", "Fecha", "Hora", "Incidencia", "H_paro", "H_arranque", "Nivel", "Niv_Arr", "Niv_Par", "V_L1", "V_L2", "V_L3"]
                df_mostrar = df_final[cols_orden].copy()
                df_mostrar['Fecha'] = df_mostrar['Fecha'].apply(lambda x: x.strftime('%d/%m/%y'))
                df_mostrar['Hora'] = df_mostrar['Hora'].apply(lambda x: x.strftime('%H:%M:%S'))
                st.dataframe(df_mostrar.style.apply(estilo_total, axis=1), use_container_width=True, hide_index=True)
            else: st.info("No hay pozos apagados.")

        with col_der:
            st.subheader("🟢 Pozos Encendidos")
            if not df_enc_full.empty:
                df_enc = df_enc_full.drop(columns=['TS', 'Incidencia'], errors='ignore')
                df_enc['Fecha'] = df_enc['Fecha'].apply(lambda x: x.strftime('%d/%m/%y'))
                df_enc['Hora'] = df_enc['Hora'].apply(lambda x: x.strftime('%H:%M:%S'))
                st.dataframe(df_enc.style.apply(estilo_total, axis=1), use_container_width=True, hide_index=True)
            else: st.info("No hay pozos operando.")
    
    t.sleep(30)
