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

# Cabecera
col_logo, col_titulo = st.columns([1, 10])
with col_logo: st.image("https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg", width=200)
with col_titulo: st.markdown('<h1 class="custom-title">Sistema de Monitoreo</h1>', unsafe_allow_html=True)

placeholder = st.empty()

while True:
    with placeholder.container():
        # --- LÓGICA DE DATOS ---
        df_dic = pd.read_sql("SELECT * FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'", ENGINE_DIC)
        tags = "', '".join(df_dic['bomba'].tolist())
        query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
        df = pd.read_sql(query, ENGINE_SCADA)
        
        # ... (Carga de mapa_inc y mapa_aux igual que antes) ...
        # (Nota: Asumiendo que ya tienes mapa_inc y mapa_aux definidos aquí como en tu código original)

        lista_apg, lista_enc = [], []
        def format_val(v): return f"{v:.2f}" if v > 0 else ""

        for _, row in df.iterrows():
            info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
            val_nivel = float(mapa_aux.get(str(info['nivel_tanque']), 0) or 0)
            data_row = {
                "Pozo": info['Pozos'], "Fecha": row['FECHA'].date(), "Hora": row['FECHA'].time(),
                "H_paro": convertir_a_hora(mapa_aux.get(str(info['H_paro']))), 
                "H_arranque": convertir_a_hora(mapa_aux.get(str(info['H_arranque']))),
                "Nivel": format_val(val_nivel), "Niv_Arr": format_val(mapa_aux.get(str(info['nivel_arranque_tq']), 0)), 
                "Niv_Par": format_val(mapa_aux.get(str(info['nivel_paro_tq']), 0)),
                "V_L1": int(float(mapa_aux.get(str(info['voltaje_L1']), 0))), 
                "V_L2": int(float(mapa_aux.get(str(info['voltaje_L2']), 0))), 
                "V_L3": int(float(mapa_aux.get(str(info['voltaje_L3']), 0)))
            }
            
            if row['VALUE'] == 0:
                data_row["Estatus_Paro"] = "⚠️ Incidencia" # simplificado para el ejemplo
                lista_apg.append(data_row)
            else:
                lista_enc.append(data_row)

        # --- VISUALIZACIÓN EN DOS COLUMNAS ---
        c_left, c_right = st.columns(2)
        
        with c_left:
            st.subheader("🔴 Pozos Apagados")
            if lista_apg:
                df_apg = pd.DataFrame(lista_apg)
                st.dataframe(df_apg, use_container_width=True, hide_index=True)
            else: st.info("Sin pozos apagados")
                
        with c_right:
            st.subheader("🟢 Pozos Encendidos")
            if lista_enc:
                df_enc = pd.DataFrame(lista_enc)
                st.dataframe(df_enc, use_container_width=True, hide_index=True)
            else: st.info("Sin pozos encendidos")

    t.sleep(30)
