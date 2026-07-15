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
    .block-container {padding-top: 0.5rem !important; padding-bottom: 0rem !important;}
    .custom-title {color: #00E5FF !important; font-size: 3.5rem; font-weight: bold; text-shadow: none !important; margin: 0; text-align: center;}
    .logo-container {display: flex; justify-content: center;}
    .dashboard-card {background-color: #0e1117; border: 1px solid #262730; border-radius: 10px; padding: 15px; text-align: center; margin: 5px;}
    .card-label {color: #ffffff; font-size: 0.9rem; margin-bottom: 10px;}
    .card-value {font-size: 1.8rem; font-weight: bold;}
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

col1, col2 = st.columns([1, 10])
with col1:
    st.markdown('<div class="logo-container">', unsafe_allow_html=True)
    st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=200)
    st.markdown('</div>', unsafe_allow_html=True)
with col2:
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
        query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID) ORDER BY h.FECHA DESC"
        df = pd.read_sql(query, ENGINE_SCADA)

        cols_aux = ['H_arranque', 'H_paro', 'nivel_tanque', 'nivel_arranque_tq', 'nivel_paro_tq', 'voltaje_L1', 'voltaje_L2', 'voltaje_L3']
        tags_aux = [str(t) for col in cols_aux for t in df_dic[col].dropna().unique()]
        query_aux = f"SELECT r.NAME, h.VALUE FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{"', '".join(tags_aux)}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
        df_h = pd.read_sql(query_aux, ENGINE_SCADA)
        mapa_aux = dict(zip(df_h['NAME'].astype(str), df_h['VALUE']))

        lista_apg, lista_enc = [], []
        def format_val(v): return f"{v:.2f}" if v > 0 else ""

        for _, row in df.iterrows():
            info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
            pozo_key = str(info['Pozos']).replace('-', '').replace(' ', '')
            inc = mapa_inc.get(pozo_key, "Sin incidencia")
            
            data_comun = {
                "Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(),
                "H_paro": convertir_a_hora(mapa_aux.get(str(info['H_paro']))), 
                "H_arranque": convertir_a_hora(mapa_aux.get(str(info['H_arranque']))),
                "Nivel": format_val(float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)),
                "Niv_Arr": format_val(float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0)),
                "Niv_Par": format_val(float(mapa_aux.get(str(info['nivel_paro_tq']), 0) or 0)),
                "V_L1": int(float(mapa_aux.get(str(info['voltaje_L1']), 0) or 0)),
                "V_L2": int(float(mapa_aux.get(str(info['voltaje_L2']), 0) or 0)),
                "V_L3": int(float(mapa_aux.get(str(info['voltaje_L3']), 0) or 0))
            }
            
            if row['VALUE'] == 0:
                estatus = f"⚠️ {inc}" if inc != "Sin incidencia" else ("✅ Normal" if (float(mapa_aux.get(str(info['nivel_arranque_tq']), 0) or 0) > 0) else "❌ Desconocida")
                data_comun.update({"Estatus_Paro": estatus, "Incidencia": inc, "TS": row['FECHA']})
                lista_apg.append(data_comun)
            else:
                lista_enc.append(data_comun)

        # --- VISUALIZACIÓN ---
        df_final = pd.DataFrame(lista_apg).sort_values(by='TS', ascending=False) if lista_apg else pd.DataFrame()
        total, normal = len(df_final), len(df_final[df_final['Estatus_Paro'].str.contains('✅')]) if not df_final.empty else 0
        incidencia = len(df_final[df_final['Estatus_Paro'].str.contains('⚠️')]) if not df_final.empty else 0
        desconocida = len(df_final[df_final['Estatus_Paro'].str.contains('❌')]) if not df_final.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1: render_card("Total Apagados", total, "#FFFFFF", "🔴")
        with c2: render_card("Estatus Normal", normal, "#00FF00", "✅")
        with c3: render_card("Por Incidencia", incidencia, "#FFD700", "⚠️")
        with c4: render_card("Desconocida", desconocida, "#FF0000", "❌")
        
        st.markdown("<br>", unsafe_allow_html=True)

        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.subheader("🔴 Pozos Apagados")
            if not df_final.empty:
                df_mostrar = df_final.drop(columns=['TS'])
                def color_text(row):
                    e = str(row['Estatus_Paro'])
                    c = '#FFD700' if '⚠️' in e else ('#00FF00' if '✅' in e else ('#FF0000' if '❌' in e else 'inherit'))
                    return [f'color: {c}'] * len(row)
                st.dataframe(df_mostrar.style.apply(color_text, axis=1), use_container_width=True, hide_index=True)
            else: st.info("No hay pozos apagados.")

        with col_der:
            st.subheader("🟢 Pozos Encendidos")
            if lista_enc:
                st.dataframe(pd.DataFrame(lista_enc), use_container_width=True, hide_index=True)
            else: st.info("No hay pozos encendidos.")

    t.sleep(30)
