import tkinter as tk
from tkinter import ttk, scrolledtext
import pandas as pd
from sqlalchemy import create_engine
import requests
import threading
from datetime import datetime, timedelta, time
import locale

# Intentar establecer el idioma en español para fechas
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass 

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

alertas_enviadas = {}

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Monitoreo MIAA 24/7")
        self.geometry("1200x750")
        
        self.horarios_manuales = {} 
        bg_color = "#1e1e1e"
        text_color = "#ffffff"
        self.configure(bg=bg_color)
        
        # --- PANEL DE EDICIÓN MANUAL ---
        self.frame_edit = tk.Frame(self, bg="#2d2d2d", pady=10)
        self.frame_edit.pack(fill=tk.X)
        
        tk.Label(self.frame_edit, text="Pozo:", fg="white", bg="#2d2d2d").pack(side=tk.LEFT, padx=5)
        self.ent_p = tk.Entry(self.frame_edit, width=10); self.ent_p.pack(side=tk.LEFT)
        tk.Label(self.frame_edit, text="Paro (HH:MM):", fg="white", bg="#2d2d2d").pack(side=tk.LEFT, padx=5)
        self.ent_paro = tk.Entry(self.frame_edit, width=10); self.ent_paro.pack(side=tk.LEFT)
        tk.Label(self.frame_edit, text="Arr (HH:MM):", fg="white", bg="#2d2d2d").pack(side=tk.LEFT, padx=5)
        self.ent_arr = tk.Entry(self.frame_edit, width=10); self.ent_arr.pack(side=tk.LEFT)
        tk.Button(self.frame_edit, text="Guardar Horario", command=self.guardar_manual).pack(side=tk.LEFT, padx=10)

        # 1. Contenedores y tablas
        self.frame_top = tk.Frame(self, pady=10, bg=bg_color)
        self.frame_top.pack(fill=tk.X)
        
        self.frame_tablas = tk.Frame(self, bg=bg_color)
        self.frame_tablas.pack(fill=tk.BOTH, expand=True, padx=10)
        
        self.tree_apg = self.crear_tabla_apg(self.frame_tablas, bg_color, text_color)
        self.tree_enc = self.crear_tabla_enc(self.frame_tablas, bg_color, text_color)
        
        # Estilos
        style = ttk.Style()
        style.theme_use('clam')
        bg_header = "#3c4043" 
        style.configure("Treeview.Heading", background=bg_header, foreground=text_color, relief="flat", padding=5, font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", background="#2d2d2d", foreground=text_color, fieldbackground="#2d2d2d", rowheight=25)
        
        self.lbl_enc = tk.Label(self.frame_top, text="Encendidos: 0", fg="#4caf50", bg=bg_color, font=("Arial", 14, "bold"))
        self.lbl_enc.pack(side=tk.RIGHT, padx=100)
        self.lbl_apg = tk.Label(self.frame_top, text="Apagados: 0", fg="#f44336", bg=bg_color, font=("Arial", 14, "bold"))
        self.lbl_apg.pack(side=tk.LEFT, padx=100)
        
        self.log_area = scrolledtext.ScrolledText(self, height=8, bg="#2d2d2d", fg=text_color, insertbackground="white")
        self.log_area.pack(fill=tk.X, padx=10, pady=10)
        
        self.actualizar_datos()

    def guardar_manual(self):
        pozo = self.ent_p.get().strip()
        self.horarios_manuales[pozo] = {"H_paro": self.ent_paro.get(), "H_arr": self.ent_arr.get()}
        self.log_area.insert(tk.END, f"Horario manual guardado para {pozo}: {self.horarios_manuales[pozo]}\n")
        self.log_area.see(tk.END)

    def crear_tabla_apg(self, parent, bg, fg):
        frame = tk.Frame(parent, bg=bg)
        frame.pack(side="left", fill=tk.BOTH, expand=True, padx=5)
        tk.Label(frame, text="APAGADOS (Atención)", font=("Arial", 10, "bold"), bg=bg, fg=fg).pack()
        
        cols = ("Pozo", 
                "Fecha", 
                "Hora", 
                "Incidencia", 
                "H_paro", "H_arranque", 
                "Nivel", 
                "Niv_Arr", 
                "Niv_Par", 
                "Estatus_Paro", 
                "V_L1", 
                "V_L2", 
                "V_L3"
        )
        
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        # Configuración de colores
        tree.tag_configure('incidencia', foreground='#FFD700') # Amarillo oro (resalta más)
        tree.tag_configure('desconocida', foreground='#FF4500') # Rojo naranja
        tree.tag_configure('normal', foreground='#32CD32')      # Verde lima
        for col in cols: tree.heading(col, text=col); tree.column(col, width=70)
        tree.pack(fill=tk.BOTH, expand=True)
        return tree
    
    def crear_tabla_enc(self, parent, bg, fg):
        frame = tk.Frame(parent, bg=bg)
        frame.pack(side="right", fill=tk.BOTH, expand=True, padx=5)
        tk.Label(frame, text="ENCENDIDOS", font=("Arial", 10, "bold"), bg=bg, fg=fg).pack()
        
        cols = ("Pozo", 
                "Fecha", 
                "Hora", 
                "H_paro", 
                "H_arranque", 
                "Nivel", 
                "Niv_Arr", 
                "Niv_Par", 
                "V_L1", 
                "V_L2", 
                "V_L3"
        )
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        for col in cols: tree.heading(col, text=col); tree.column(col, width=70)
        tree.pack(fill=tk.BOTH, expand=True)
        return tree      

    def convertir_a_hora(self, valor):
        try:
            m = float(valor)
            return time(int((m // 60) % 24), int(m % 60))
        except: return time(0, 0)

    def es_periodo_de_paro_programado(self, t_par, t_arr):
        if t_par == time(0, 0) and t_arr == time(0, 0): return False
        ahora = datetime.now().time()
        if t_par < t_arr:
            return t_par <= ahora <= t_arr
        else:
            return ahora >= t_par or ahora <= t_arr
        
    def enviar_alerta(self, pozo, nivel, nivel_arr, fecha, hora, h_paro, h_arranque, razon):
        mensaje = (
            f"📢 <b>Reporte Automatico Miaa</b>\n"
            f"________________________________\n"
            f"⚠️ <b>Alerta:</b> Bomba Apagada\n"
            f"📍 <b>Pozo:</b> {pozo}\n"
            f"⏳ <b>Hora del paro:</b> {hora}\n"
            f"💧 <b>Nivel Tanque:</b> {nivel} mts.\n"
            f"↕️ <b>Nivel Arranque con TQ:</b> {nivel_arr} mts.\n"          
            f"⏲️ <b>Horario de Op:</b> {h_paro} - {h_arranque}\n"
            f"🔍 <b>Motivo:</b> {razon}" # Línea agregada para la razón
        )
        def send():
            try:
                query = "SELECT chart_id FROM Diccionario_telegram WHERE activo = 'Si'"
                df_ids = pd.read_sql(query, ENGINE_DIC)
                lista_ids = df_ids['chart_id'].tolist()
                for chat_id in lista_ids:
                    try:
                        requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
                    except: continue
            except: pass
        threading.Thread(target=send, daemon=True).start()

    def actualizar_datos(self):
        try:
            def obtener_datos(query, engine):
                try: return pd.read_sql(query, engine)
                except Exception: engine.dispose(); return pd.read_sql(query, engine)

            # 1. Asegúrate de que Diccionario_de_pozos tenga columnas: voltaje_L1, voltaje_L2, voltaje_L3
            query_dic = "SELECT Pozos, bomba, H_arranque, H_paro, nivel_tanque, nivel_arranque_tq, nivel_paro_tq, voltaje_L1, voltaje_L2, voltaje_L3 FROM Diccionario_de_pozos WHERE bomba != 'Sin telemetria'"
            df_dic = obtener_datos(query_dic, ENGINE_DIC)
            tags_str = "', '".join(df_dic['bomba'].tolist())
            
            df_inc = obtener_datos("SELECT NUM_POZO, DIAGNOSTICO_FALLA FROM vw_incidencias_en_pozos WHERE ESTATUS != 'Cerrada'", ENGINE_SCADA)
            df_inc['P_LIMPIO'] = df_inc['NUM_POZO'].str.replace('-', '', regex=False)
            mapa_inc = dict(zip(df_inc['P_LIMPIO'], df_inc['DIAGNOSTICO_FALLA']))

            query = f"SELECT r.NAME, h.VALUE, h.FECHA FROM VfiTagNumHistory_Ultimo h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)"
            df = obtener_datos(query, ENGINE_SCADA).sort_values(by='FECHA', ascending=True)
            
            # CORRECCIÓN: Se agregan los tags de voltaje a la lista correctamente usando +
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

            self.tree_apg.delete(*self.tree_apg.get_children())
            self.tree_enc.delete(*self.tree_enc.get_children())
            
            enc, apg, ahora_dt = 0, 0, datetime.now()
            
            for _, row in df.iterrows():
                info = df_dic[df_dic['bomba'] == row['NAME']].iloc[0]
                pozo = info['Pozos']
                
                # Extraer voltajes dinámicamente según el pozo
                v1 = mapa_aux.get(info['voltaje_L1'], 0)
                v2 = mapa_aux.get(info['voltaje_L2'], 0)
                v3 = mapa_aux.get(info['voltaje_L3'], 0)
                
                v1 = f"{float(v1):.1f}"
                v2 = f"{float(v2):.1f}"
                v3 = f"{float(v3):.1f}"
                
                inc = mapa_inc.get(pozo.replace('-', ''), "Sin incidencia")
                f = row['FECHA'].strftime('%d de %B de %Y')
                h = row['FECHA'].strftime('%H:%M:%S')
                
                t_arr = self.convertir_a_hora(mapa_aux.get(info['H_arranque'], 0))
                t_par = self.convertir_a_hora(mapa_aux.get(info['H_paro'], 0))
                
                nivel_act = mapa_aux.get(info['nivel_tanque'])
                niv_arr = mapa_aux.get(info['nivel_arranque_tq'])
                nivel_act_str = f"{float(nivel_act):.2f}" if nivel_act is not None else "Directo a Red"
                niv_arr_str = f"{float(niv_arr):.2f}" if niv_arr is not None else ""
                niv_par_str = f"{float(mapa_aux.get(info['nivel_paro_tq'])):.2f}" if mapa_aux.get(info['nivel_paro_tq']) is not None else ""
               
                
                
                if row['VALUE'] == 0:
                    apg += 1
                    es_paro_programado = self.es_periodo_de_paro_programado(t_par, t_arr)
                    
                    # 1. Cálculos de rangos de nivel
                    nivel_val = float(nivel_act) if nivel_act is not None else 0
                    niv_arr_val = float(niv_arr) if niv_arr is not None else 0
                    niv_par_val = float(mapa_aux.get(info['nivel_paro_tq'], 0)) if mapa_aux.get(info['nivel_paro_tq']) is not None else 0
                    
                    # Definición del umbral (50% del nivel de arranque)
                    umbral_inferior = niv_arr_val * 0.50
                    
                    # Definimos estados específicos usando el umbral
                    # Se considera "No arranca por nivel bajo" si es menor al umbral
                    es_paro_por_nivel_bajo = (nivel_val < umbral_inferior and niv_arr_val > 0)
                    es_paro_por_nivel_alto = (nivel_val >= niv_par_val and niv_par_val > 0)
                    
                    # Es "Normal por nivel" si está en el rango operativo válido
                    es_normal_por_nivel = (nivel_val >= umbral_inferior and nivel_val < niv_par_val)
                    
                    # 2. Lógica de Estatus (Orden de prioridad)
                    if inc.lower().strip() != "sin incidencia":
                        estatus_paro = "⚠️ Parado por incidencia"
                        tag_asignado = 'incidencia'
                        razon_alerta = inc
                    elif es_paro_programado or es_paro_por_nivel_alto or es_normal_por_nivel:
                        # Si está en rango normal o paro por nivel alto/programado, es ✅ Normal
                        estatus_paro = "✅ Normal"
                        tag_asignado = 'normal'
                        razon_alerta = "Operación normal"
                    elif es_paro_por_nivel_bajo:
                        # Si está por debajo del umbral, marca como falla de nivel
                        estatus_paro = "No arranca con su condición de tanque"
                        tag_asignado = 'desconocida'
                        razon_alerta = "No arranca con su condición de tanque"
                    else:
                        estatus_paro = "❌ Desconocida"
                        tag_asignado = 'desconocida'
                        razon_alerta = "Estatus desconocido"
                    
                    self.tree_apg.insert("", tk.END, 
                                         values=(pozo, 
                                                 f, 
                                                 h, 
                                                 inc, 
                                                 t_par
                                                 .strftime('%H:%M'), 
                                                 t_arr.strftime('%H:%M'), 
                                                 nivel_act_str, 
                                                 niv_arr_str, 
                                                 niv_par_str, 
                                                 estatus_paro,
                                                 v1, v2, v3), 
                                         tags=(tag_asignado,))
                    
                    # 3. Lógica de Alertas (Solo si es paro por nivel bajo o incidencia real)
                    es_hoy = row['FECHA'].date() == ahora_dt.date()
                    
                    # FILTRO MAESTRO: Si es "Operación normal", NO hacemos nada. 
                    # Solo procesamos si es una falla real o estado desconocido persistente.
                    if es_hoy and inc.lower().strip() == "sin incidencia" and razon_alerta != "Operación normal":
                        
                        # Definimos qué merece alerta:
                        # 1. Paro por nivel bajo (siempre que no sea normal)
                        # 2. Estatus desconocido (siempre que no sea normal)
                        if es_paro_por_nivel_bajo or estatus_paro == "❌ Desconocida":
                            
                            if pozo not in alertas_enviadas:
                                if (ahora_dt - row['FECHA']) > timedelta(minutes=60):
                                    self.enviar_alerta(pozo, nivel_act_str, niv_arr_str, f, h, t_par.strftime('%H:%M'), t_arr.strftime('%H:%M'), razon_alerta)
                                    alertas_enviadas[pozo] = ahora_dt
                                    self.log_area.insert(tk.END, f"Alerta enviada: {pozo} | {razon_alerta}\n")
                                    self.log_area.see(tk.END)
                else:
                    enc += 1
                    self.tree_enc.insert("", tk.END, 
                                         values=(pozo, 
                                                 f, 
                                                 h, 
                                                 t_par.strftime('%H:%M'), 
                                                 t_arr.strftime('%H:%M'), 
                                                 nivel_act_str, 
                                                 niv_arr_str, 
                                                 niv_par_str,
                                                 v1, v2, v3)
                                         )
                    
                    if pozo in alertas_enviadas: del alertas_enviadas[pozo]
            
            self.lbl_enc.config(text=f"Encendidos: {enc}")
            self.lbl_apg.config(text=f"Apagados: {apg}")
            
        except Exception as e:
            self.log_area.insert(tk.END, f"Error: {e}\n")
        self.after(60000, self.actualizar_datos)

if __name__ == "__main__":
    App().mainloop()