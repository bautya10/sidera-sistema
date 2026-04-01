"""
SISTEMA SIDERA - Versión Profesional
Sin tosquedades, sin reloads, UI fluida
"""

import streamlit as st
import sqlite3
import zipfile
import io
import os
import time
import json
import re
import base64
import difflib
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import anthropic

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

st.set_page_config(
    page_title="Sistema Sidera",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Session State
if 'editando_id' not in st.session_state:
    st.session_state.editando_id = None
if 'mensajes' not in st.session_state:
    st.session_state.mensajes = []
if 'ultimo_scroll' not in st.session_state:
    st.session_state.ultimo_scroll = 0

# Constantes
DB_NAME = "sidera_datos.db"
CLIENTES_FONDEO = ['Celso', 'Vertice', 'Canella', '3D Land', 'Moreira', 'Giampaoli', 'Otro']
CLIENTES_MOSTRADOR = ['Giardino', 'Fimex', 'Alcaide', 'Red Bird', 'Parra', 'Moreira', 'Giampaoli', 'Manu Camps Salta', 'CC General', 'Ajustes Manuales']
CLIENTES_EXTRACTOR = ["Celso", "Canella", "Vertice", "3D Land", "Moreira", "Giampaoli", "Otro"]

def _cargar_env_local():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

_cargar_env_local()

# =============================================================================
# CSS PROFESIONAL
# =============================================================================

def cargar_css():
    st.markdown("""
    <style>
        /* General */
        .main { background-color: #f8f9fa; padding: 1rem 2rem; }
        .block-container { max-width: 1400px; padding-top: 1rem; }
        
        /* Ocultar elementos innecesarios */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display: none;}
        header {visibility: hidden;}
        
        /* Semáforos */
        .semaforo {
            background: white;
            border-radius: 8px;
            padding: 1.2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 1rem;
        }
        
        .semaforo.verde { border-left: 4px solid #28a745; }
        .semaforo.rojo { border-left: 4px solid #dc3545; }
        
        .kpi {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 16px;
            font-weight: 600;
            font-size: 0.95rem;
        }
        
        .kpi.verde { background: #28a745; color: white; }
        .kpi.rojo { background: #dc3545; color: white; }
        .kpi.gris { background: #e9ecef; color: #6c757d; }
        
        /* Mensajes */
        .mensaje {
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 1rem;
            border-left: 4px solid;
            font-weight: 500;
        }
        
        .mensaje.success { background: #d1e7dd; color: #0f5132; border-color: #28a745; }
        .mensaje.warning { background: #fff3cd; color: #664d03; border-color: #ffc107; }
        .mensaje.error { background: #f8d7da; color: #842029; border-color: #dc3545; }
        .mensaje.info { background: #cfe2ff; color: #084298; border-color: #0d6efd; }
        
        /* Tablas mejoradas */
        .stDataFrame { 
            border: 1px solid #dee2e6;
            border-radius: 8px;
            overflow: hidden;
        }
        
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 2px;
            background-color: white;
            border-radius: 8px 8px 0 0;
            padding: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            background-color: transparent;
            border: none;
            border-radius: 6px;
            color: #6c757d;
            font-weight: 600;
            padding: 12px 20px;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #0d6efd !important;
            color: white !important;
        }
        
        /* Botones mejorados */
        .stButton button {
            border-radius: 6px;
            font-weight: 600;
            border: none;
            transition: all 0.2s;
        }
        
        .stButton button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        
        /* Estados en tabla */
        .estado-pendiente { color: #6c757d; }
        .estado-sugerido { color: #ffc107; }
        .estado-completado { color: #28a745; }
        
        /* Scroll suave */
        html {
            scroll-behavior: smooth;
        }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# BD
# =============================================================================

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                solicitante TEXT NOT NULL,
                sub_cliente TEXT,
                titular TEXT NOT NULL,
                monto REAL NOT NULL,
                estado TEXT NOT NULL,
                fecha_pedido TEXT NOT NULL,
                nivel_alerta TEXT,
                datos_extraidos TEXT,
                id_operacion TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saldos_diarios (
                fecha TEXT PRIMARY KEY,
                nexo_ingresos REAL DEFAULT 0,
                nexo_egresos REAL DEFAULT 0
            )
        ''')
        conn.commit()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# UTILIDADES
# =============================================================================

def limpiar_nombre(nombre: str) -> str:
    if not nombre:
        return ""
    return nombre.replace(",", "").strip()

def limpiar_monto(monto_str: str) -> float:
    if not monto_str:
        return 0.0
    monto = re.sub(r'[$USD€ARS\s]', '', str(monto_str))
    if re.search(r'[.,]\d{2}$', monto):
        if '.' in monto and ',' in monto:
            if monto.rindex('.') > monto.rindex(','):
                monto = monto.replace(',', '')
                monto = monto.replace('.', ',')
            else:
                monto = monto.replace('.', '')
        elif '.' in monto:
            monto = monto.replace('.', ',')
    else:
        monto = monto.replace('.', '').replace(',', '')
    monto = monto.replace(',', '.')
    try:
        return float(monto)
    except:
        return 0.0

def pdf_a_imagen_png(pdf_bytes: bytes) -> bytes:
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pagina = doc[0]
    mat = fitz.Matrix(2.0, 2.0)
    pix = pagina.get_pixmap(matrix=mat)
    return pix.tobytes("png")

def extraer_datos_con_vision_api(archivo_contenido: bytes, nombre_archivo: str, tipo_archivo: str) -> Dict[str, str]:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", None) if hasattr(st, "secrets") else None
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return {"emisor": "", "monto": "0", "destinatario": "", "id_operacion": "", "fecha": "", "horario": "", "monto_float": 0.0}
    
    try:
        client = anthropic.Anthropic(api_key=api_key)

        if tipo_archivo == 'application/pdf' or nombre_archivo.lower().endswith('.pdf'):
            try:
                archivo_contenido = pdf_a_imagen_png(archivo_contenido)
                media_type = 'image/png'
            except:
                return {"emisor": "", "monto": "0", "destinatario": "", "id_operacion": "", "fecha": "", "horario": "", "monto_float": 0.0}
        elif tipo_archivo in ['image/jpeg', 'image/jpg']:
            media_type = 'image/jpeg'
        elif tipo_archivo == 'image/png':
            media_type = 'image/png'
        else:
            media_type = 'image/jpeg'

        base64_data = base64.b64encode(archivo_contenido).decode('utf-8')

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64_data}},
                    {"type": "text", "text": '''Analiza este comprobante y extrae: emisor (quien envía), monto, destinatario (quien recibe), id_operacion, fecha (YYYY-MM-DD), horario (HH:MM:SS). Responde SOLO JSON válido sin texto extra.

Ejemplo:
{
    "emisor": "Juan Pérez",
    "monto": "$1.500,00",
    "destinatario": "María González",
    "id_operacion": "123456789",
    "fecha": "2024-02-11",
    "horario": "14:30:00"
}'''}
                ]
            }]
        )
        
        response_text = message.content[0].text.strip().replace('```json', '').replace('```', '').strip()
        datos = json.loads(response_text)
        
        for clave in ["emisor", "monto", "destinatario", "id_operacion", "fecha", "horario"]:
            if clave not in datos:
                datos[clave] = ""
        
        datos['monto_float'] = limpiar_monto(datos.get('monto', '0'))
        return datos
        
    except:
        return {"emisor": "", "monto": "0", "destinatario": "", "id_operacion": "", "fecha": "", "horario": "", "monto_float": 0.0}

def extraer_archivos_zip(archivo_zip: bytes) -> List[Tuple[str, bytes, str]]:
    archivos = []
    try:
        with zipfile.ZipFile(io.BytesIO(archivo_zip), 'r') as zip_ref:
            filelist_ordenada = sorted(zip_ref.filelist, key=lambda x: x.filename)
            for file_info in filelist_ordenada:
                if not file_info.is_dir():
                    nombre = file_info.filename
                    if '__MACOSX' in nombre or nombre.startswith('.'):
                        continue
                    contenido = zip_ref.read(nombre)
                    extension = Path(nombre).suffix.lower()
                    if extension in ['.jpg', '.jpeg']:
                        tipo_mime = 'image/jpeg'
                    elif extension == '.png':
                        tipo_mime = 'image/png'
                    elif extension == '.pdf':
                        tipo_mime = 'application/pdf'
                    else:
                        continue
                    archivos.append((nombre, contenido, tipo_mime))
    except:
        pass
    return archivos

def similitud_textos(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

def generar_doble_partida(emisor: str, monto: str, id_op: str, cliente: str) -> Dict[str, str]:
    resultado = {}
    resultado["nexo"] = f'"{emisor}",,,,,,,,{monto}'
    if cliente == "Celso":
        resultado["cliente"] = f'"{emisor}",{id_op},,,,,,,,,{monto}'
    else:
        resultado["cliente"] = f'"{emisor}",,,,,{monto}'
    return resultado

# =============================================================================
# MENSAJES
# =============================================================================

def mostrar_mensajes():
    if st.session_state.mensajes:
        for tipo, msg in st.session_state.mensajes:
            st.markdown(f'<div class="mensaje {tipo}">{msg}</div>', unsafe_allow_html=True)
        st.session_state.mensajes = []

def agregar_mensaje(tipo, mensaje):
    if (tipo, mensaje) not in st.session_state.mensajes:
        st.session_state.mensajes.append((tipo, mensaje))

# =============================================================================
# MODAL EDICIÓN
# =============================================================================

@st.dialog("✏️ Editar Registro")
def modal_editar(transaccion_id):
    conn = get_db_connection()
    trans = conn.execute("SELECT * FROM transacciones WHERE id = ?", (transaccion_id,)).fetchone()
    
    if not trans:
        st.error("Registro no encontrado")
        return
    
    clientes = CLIENTES_MOSTRADOR if trans['tipo'] == 'SALIDA' else CLIENTES_FONDEO
    
    nuevo_cliente = st.selectbox(
        "Cliente",
        clientes,
        index=clientes.index(trans['solicitante']) if trans['solicitante'] in clientes else 0
    )
    
    nuevo_titular = st.text_input("Titular", value=trans['titular'])
    nuevo_monto = st.text_input("Monto", value=str(trans['monto']))
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Guardar", type="primary", use_container_width=True):
            if nuevo_cliente and nuevo_titular and nuevo_monto:
                try:
                    monto_float = limpiar_monto(nuevo_monto)
                    conn.execute(
                        "UPDATE transacciones SET solicitante = ?, titular = ?, monto = ? WHERE id = ?",
                        (nuevo_cliente, nuevo_titular, monto_float, transaccion_id)
                    )
                    conn.commit()
                    agregar_mensaje("success", "✅ Cambios guardados")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("⚠️ Completá todos los campos")
    
    with col2:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    
    conn.close()

# =============================================================================
# FUNCIONES DE ACCIONES (con callbacks para evitar reload)
# =============================================================================

def marcar_completado(id_trans):
    conn = get_db_connection()
    conn.execute("UPDATE transacciones SET estado = 'COMPLETADO' WHERE id = ?", (id_trans,))
    conn.commit()
    conn.close()
    agregar_mensaje("success", "✅ Marcado como completado")

def rechazar_match(id_trans):
    conn = get_db_connection()
    conn.execute(
        "UPDATE transacciones SET estado = 'PENDIENTE', nivel_alerta = NULL, datos_extraidos = NULL, id_operacion = NULL WHERE id = ?",
        (id_trans,)
    )
    conn.commit()
    conn.close()
    agregar_mensaje("warning", "⏳ Vuelto a pendiente")

def eliminar_transaccion(id_trans):
    conn = get_db_connection()
    conn.execute("DELETE FROM transacciones WHERE id = ?", (id_trans,))
    conn.commit()
    conn.close()
    agregar_mensaje("info", "🗑️ Eliminado")

# =============================================================================
# SEMÁFOROS
# =============================================================================

def mostrar_semaforos(dia_formato):
    conn = get_db_connection()
    
    saldos = conn.execute("SELECT * FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
    nexo_ing = saldos['nexo_ingresos'] if saldos else 0
    nexo_egr = saldos['nexo_egresos'] if saldos else 0
    
    sis_ing = conn.execute("SELECT SUM(monto) FROM transacciones WHERE tipo='ENTRADA' AND fecha_pedido LIKE ?", (f'{dia_formato}%',)).fetchone()[0] or 0
    sis_egr = conn.execute("SELECT SUM(monto) FROM transacciones WHERE tipo='SALIDA' AND estado='COMPLETADO' AND fecha_pedido LIKE ?", (f'{dia_formato}%',)).fetchone()[0] or 0
    
    comision = sis_egr * 0.0075
    total_egr = sis_egr + comision
    
    dif_ing = nexo_ing - sis_ing
    dif_egr = nexo_egr - total_egr
    
    col1, col2 = st.columns(2)
    
    with col1:
        kpi_class = "verde" if abs(dif_ing) < 1 and sis_ing > 0 else ("gris" if abs(dif_ing) < 1 else "rojo")
        
        st.markdown(f"""
        <div class="semaforo verde">
            <h5 style="color: #28a745; margin: 0 0 1rem 0;">📥 INGRESOS</h5>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; align-items: center;">
                <div>
                    <small style="color: #6c757d; font-weight: 600;">Nexo:</small>
                    <div style="font-size: 1.3rem; font-weight: 700; color: #28a745; margin-top: 0.3rem;">${nexo_ing:,.0f}</div>
                </div>
                <div style="text-align: center;">
                    <small style="color: #6c757d; font-weight: 600;">Sistema:</small>
                    <div style="font-size: 1.3rem; font-weight: 700; margin-top: 0.3rem;">${sis_ing:,.0f}</div>
                </div>
                <div style="text-align: right;">
                    <small style="color: #6c757d; font-weight: 600;">Diferencia:</small>
                    <div style="margin-top: 0.3rem;">
                        <span class="kpi {kpi_class}">{'✅ $0' if abs(dif_ing) < 1 else f'❌ ${dif_ing:,.0f}'}</span>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        kpi_class = "verde" if abs(dif_egr) < 1 and total_egr > 0 else ("gris" if abs(dif_egr) < 1 else "rojo")
        
        st.markdown(f"""
        <div class="semaforo rojo">
            <h5 style="color: #dc3545; margin: 0 0 1rem 0;">📤 EGRESOS</h5>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; align-items: center;">
                <div>
                    <small style="color: #6c757d; font-weight: 600;">Nexo:</small>
                    <div style="font-size: 1.3rem; font-weight: 700; color: #dc3545; margin-top: 0.3rem;">${nexo_egr:,.0f}</div>
                </div>
                <div style="text-align: center;">
                    <small style="color: #6c757d; font-weight: 600;">Sistema:</small>
                    <div style="margin-top: 0.3rem;">
                        <div style="font-weight: 600;">${sis_egr:,.0f}</div>
                        <small style="color: #6c757d;">+ 0.75%: ${comision:,.0f}</small>
                        <div style="font-size: 1.1rem; font-weight: 700; border-top: 2px solid #dee2e6; padding-top: 0.25rem; margin-top: 0.25rem;">${total_egr:,.0f}</div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <small style="color: #6c757d; font-weight: 600;">Diferencia:</small>
                    <div style="margin-top: 0.3rem;">
                        <span class="kpi {kpi_class}">{'✅ $0' if abs(dif_egr) < 1 else f'❌ ${dif_egr:,.0f}'}</span>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    conn.close()

# =============================================================================
# TAB MOSTRADOR
# =============================================================================

def tab_mostrador(dia_formato):
    conn = get_db_connection()
    
    col_left, col_right = st.columns([1, 3])
    
    with col_left:
        st.markdown("### 📝 Anotar Pedido")
        
        with st.form("form_pedido", clear_on_submit=True):
            solicitante = st.selectbox("Cliente", [""] + CLIENTES_MOSTRADOR)
            
            sub_cliente = ""
            if solicitante == "CC General":
                sub_cliente = st.text_input("Nombre específico")
            
            titular = st.text_input("Titular")
            monto_texto = st.text_input("Monto")
            
            if st.form_submit_button("Guardar", type="primary", use_container_width=True):
                if not solicitante:
                    agregar_mensaje("warning", "⚠️ Seleccioná un cliente")
                elif not titular.strip():
                    agregar_mensaje("warning", "⚠️ Completá el titular")
                elif not monto_texto.strip():
                    agregar_mensaje("warning", "⚠️ Completá el monto")
                elif solicitante == "CC General" and not sub_cliente.strip():
                    agregar_mensaje("warning", "⚠️ CC General requiere nombre específico")
                else:
                    try:
                        monto_float = limpiar_monto(monto_texto)
                        if monto_float <= 0:
                            agregar_mensaje("warning", "⚠️ Monto debe ser mayor a 0")
                        else:
                            estado = "COMPLETADO" if solicitante == 'Ajustes Manuales' else "PENDIENTE"
                            conn.execute(
                                "INSERT INTO transacciones (tipo, solicitante, sub_cliente, titular, monto, estado, fecha_pedido) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                ("SALIDA", solicitante, sub_cliente, titular, monto_float, estado, datetime.now().strftime("%d/%m/%Y %H:%M"))
                            )
                            conn.commit()
                            agregar_mensaje("success", "✅ Pedido guardado")
                            st.rerun()
                    except:
                        agregar_mensaje("error", "❌ Monto inválido")
        
        st.markdown("---")
        st.markdown("### 📥 Buscar Matches")
        
        archivos_match = st.file_uploader(
            "Archivos",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="match_files"
        )
        
        if st.button("🚀 Disparar Búsqueda", type="primary", use_container_width=True):
            if not archivos_match:
                agregar_mensaje("warning", "⚠️ No subiste archivos")
            else:
                with st.spinner("Analizando..."):
                    archivos_a_procesar = []
                    for archivo in archivos_match:
                        contenido = archivo.read()
                        if archivo.name.lower().endswith('.zip'):
                            archivos_zip = extraer_archivos_zip(contenido)
                            archivos_a_procesar.extend(archivos_zip)
                        else:
                            archivos_a_procesar.append((archivo.name, contenido, archivo.type))
                    
                    if archivos_a_procesar:
                        matches = 0
                        for nombre, contenido, tipo in archivos_a_procesar:
                            try:
                                datos = extraer_datos_con_vision_api(contenido, nombre, tipo)
                                monto = datos.get('monto_float', 0.0)
                                dest = datos.get('destinatario', '')
                                id_op = datos.get('id_operacion', '')
                                
                                if id_op:
                                    existe = conn.execute("SELECT id FROM transacciones WHERE id_operacion = ? AND estado = 'COMPLETADO'", (id_op,)).fetchone()
                                    if existe:
                                        continue
                                
                                posibles = conn.execute("SELECT * FROM transacciones WHERE estado = 'PENDIENTE' AND monto = ?", (monto,)).fetchall()
                                
                                if posibles:
                                    mejor = max(posibles, key=lambda p: similitud_textos(p['titular'], dest))
                                    similitud = similitud_textos(mejor['titular'], dest)
                                    nivel = 'AMARILLO' if not dest or similitud < 0.4 else 'VERDE'
                                    conn.execute(
                                        "UPDATE transacciones SET estado = 'SUGERIDO', nivel_alerta = ?, datos_extraidos = ?, id_operacion = ? WHERE id = ?",
                                        (nivel, f"Leído: '{dest or 'N/A'}'", id_op, mejor['id'])
                                    )
                                    matches += 1
                                
                                time.sleep(0.3)
                            except:
                                pass
                        
                        conn.commit()
                        if matches > 0:
                            agregar_mensaje("success", f"✅ {matches} match(es)")
                        else:
                            agregar_mensaje("info", "ℹ️ Sin matches")
                        st.rerun()
    
    with col_right:
        st.markdown("### Transferencias del Día")
        
        salidas = conn.execute(
            "SELECT * FROM transacciones WHERE tipo = 'SALIDA' AND (fecha_pedido LIKE ? OR estado IN ('PENDIENTE', 'SUGERIDO')) ORDER BY CASE WHEN estado = 'PENDIENTE' THEN 1 WHEN estado = 'SUGERIDO' THEN 2 ELSE 3 END, id DESC",
            (f'{dia_formato}%',)
        ).fetchall()
        
        if salidas:
            # Convertir a DataFrame
            data = []
            for s in salidas:
                estado_icon = "⚪" if s['estado'] == 'PENDIENTE' else ("🟡" if s['estado'] == 'SUGERIDO' else "🟢")
                estado_text = f"{estado_icon} {s['estado']}"
                
                data.append({
                    'ID': s['id'],
                    'Estado': estado_text,
                    'Cliente': s['solicitante'],
                    'Titular': s['titular'],
                    'Monto': f"${s['monto']:,.2f}",
                    'Análisis': s['datos_extraidos'] or '---'
                })
            
            df = pd.DataFrame(data)
            
            # Mostrar DataFrame
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "Estado": st.column_config.TextColumn("Estado", width="medium"),
                    "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
                    "Titular": st.column_config.TextColumn("Titular", width="medium"),
                    "Monto": st.column_config.TextColumn("Monto", width="small"),
                    "Análisis": st.column_config.TextColumn("Análisis IA", width="large")
                }
            )
            
            # Botones por fila
            st.markdown("**Acciones:**")
            for s in salidas:
                cols = st.columns([2, 2, 2, 2, 2, 1, 6])
                
                with cols[0]:
                    st.write(f"#{s['id']}")
                
                if s['estado'] == 'PENDIENTE':
                    with cols[1]:
                        if st.button("✔️ OK", key=f"ok_{s['id']}", on_click=marcar_completado, args=(s['id'],)):
                            pass
                    with cols[2]:
                        if st.button("✏️", key=f"edit_{s['id']}"):
                            modal_editar(s['id'])
                    with cols[3]:
                        if st.button("🗑️", key=f"del_{s['id']}", on_click=eliminar_transaccion, args=(s['id'],)):
                            pass
                
                elif s['estado'] == 'SUGERIDO':
                    with cols[1]:
                        if st.button("✔️ OK", key=f"ok_sug_{s['id']}", on_click=marcar_completado, args=(s['id'],)):
                            pass
                    with cols[2]:
                        if st.button("❌", key=f"no_sug_{s['id']}", on_click=rechazar_match, args=(s['id'],)):
                            pass
                    with cols[3]:
                        if st.button("🗑️", key=f"del_sug_{s['id']}", on_click=eliminar_transaccion, args=(s['id'],)):
                            pass
                
                else:  # COMPLETADO
                    with cols[1]:
                        st.write("✔️ OK")
                    with cols[2]:
                        if st.button("🗑️", key=f"del_comp_{s['id']}", on_click=eliminar_transaccion, args=(s['id'],)):
                            pass
        else:
            st.info("ℹ️ No hay transferencias")
    
    conn.close()

# =============================================================================
# TAB HISTORIAL (CON DATA_EDITOR PROFESIONAL)
# =============================================================================

def tab_historial():
    conn = get_db_connection()
    
    st.markdown("### ✅ Auditoría General")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filtro_tipo = st.selectbox("Tipo", ["TODOS", "ENTRADA", "SALIDA"])
    
    with col2:
        todos_clientes = sorted(list(set(CLIENTES_FONDEO + CLIENTES_MOSTRADOR)))
        filtro_cliente = st.selectbox("Cliente", ["TODOS"] + todos_clientes)
    
    with col3:
        buscar = st.text_input("🔍 Buscar")
    
    # Query
    query = "SELECT * FROM transacciones WHERE estado = 'COMPLETADO'"
    params = []
    
    if filtro_tipo != "TODOS":
        query += " AND tipo = ?"
        params.append(filtro_tipo)
    
    if filtro_cliente != "TODOS":
        query += " AND solicitante = ?"
        params.append(filtro_cliente)
    
    if buscar:
        query += " AND (titular LIKE ? OR CAST(monto AS TEXT) LIKE ?)"
        params.append(f'%{buscar}%')
        params.append(f'%{buscar}%')
    
    query += " ORDER BY fecha_pedido DESC"
    
    resultados = conn.execute(query, params).fetchall()
    
    if resultados:
        # Convertir a DataFrame para data_editor
        data = []
        for r in resultados:
            data.append({
                'Seleccionar': False,
                'ID': r['id'],
                'Fecha': r['fecha_pedido'],
                'Tipo': r['tipo'],
                'Cliente': r['solicitante'],
                'Titular': r['titular'],
                'Monto': f"${r['monto']:,.2f}",
                'ID Op': r['id_operacion'] or 'N/A'
            })
        
        df = pd.DataFrame(data)
        
        # Editor interactivo
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn(
                    "☑",
                    help="Seleccionar para borrar",
                    default=False,
                    width="small"
                ),
                "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "Fecha": st.column_config.TextColumn("Fecha", disabled=True, width="medium"),
                "Tipo": st.column_config.TextColumn("Tipo", disabled=True, width="small"),
                "Cliente": st.column_config.TextColumn("Cliente", disabled=True, width="medium"),
                "Titular": st.column_config.TextColumn("Titular", disabled=True, width="medium"),
                "Monto": st.column_config.TextColumn("Monto", disabled=True, width="small"),
                "ID Op": st.column_config.TextColumn("ID Op", disabled=True, width="small")
            },
            disabled=["ID", "Fecha", "Tipo", "Cliente", "Titular", "Monto", "ID Op"],
            key="editor_historial"
        )
        
        # Botón borrar seleccionados
        seleccionados = edited_df[edited_df['Seleccionar'] == True]
        
        if len(seleccionados) > 0:
            if st.button(f"🗑️ Borrar ({len(seleccionados)}) seleccionados", type="primary"):
                ids_borrar = seleccionados['ID'].tolist()
                for id_borrar in ids_borrar:
                    conn.execute("DELETE FROM transacciones WHERE id = ?", (id_borrar,))
                conn.commit()
                agregar_mensaje("info", f"🗑️ {len(ids_borrar)} registros eliminados")
                st.rerun()
    else:
        st.info("ℹ️ No hay registros")
    
    conn.close()

# =============================================================================
# TABS ADICIONALES (Fondeo y Extractor)
# =============================================================================

def tab_fondeo(dia_formato):
    st.markdown("### 📥 Fondeo Directo")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        cliente_fondeo = st.selectbox("Quién envía", [""] + CLIENTES_FONDEO)
    
    with col2:
        archivos_fondeo = st.file_uploader(
            "Archivos",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="fondeo_files"
        )
    
    if st.button("⚙️ Procesar", type="primary"):
        if not cliente_fondeo or not archivos_fondeo:
            agregar_mensaje("warning", "⚠️ Completá todos los campos")
        else:
            conn = get_db_connection()
            
            with st.spinner("Procesando..."):
                archivos_a_procesar = []
                for archivo in archivos_fondeo:
                    contenido = archivo.read()
                    if archivo.name.lower().endswith('.zip'):
                        archivos_zip = extraer_archivos_zip(contenido)
                        archivos_a_procesar.extend(archivos_zip)
                    else:
                        archivos_a_procesar.append((archivo.name, contenido, archivo.type))
                
                insertados = 0
                duplicados = 0
                
                for nombre, contenido, tipo in archivos_a_procesar:
                    try:
                        datos = extraer_datos_con_vision_api(contenido, nombre, tipo)
                        
                        emisor = limpiar_nombre(datos.get("emisor", ""))
                        if not emisor:
                            emisor = datos.get("id_operacion", "") or "SIN_EMISOR"
                        
                        monto = datos.get('monto_float', 0.0)
                        id_op = datos.get('id_operacion', '')
                        
                        if not id_op or not id_op.strip():
                            id_op = f"SIN_ID_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                        
                        existe = conn.execute("SELECT id FROM transacciones WHERE id_operacion = ?", (id_op,)).fetchone()
                        
                        if existe:
                            duplicados += 1
                        else:
                            conn.execute(
                                "INSERT INTO transacciones (tipo, solicitante, sub_cliente, titular, monto, estado, fecha_pedido, id_operacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                ("ENTRADA", cliente_fondeo, "", emisor, monto, "COMPLETADO", datetime.now().strftime("%d/%m/%Y %H:%M"), id_op)
                            )
                            insertados += 1
                        
                        time.sleep(0.3)
                    except:
                        pass
                
                conn.commit()
                
                if insertados > 0:
                    agregar_mensaje("success", f"✅ {insertados} fondeo(s)")
                if duplicados > 0:
                    agregar_mensaje("warning", f"⚠️ {duplicados} duplicado(s)")
                
                st.rerun()
            
            conn.close()

def tab_extractor():
    st.markdown("### 🔄 Extractor + Doble Partida")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        cliente = st.selectbox("Cliente", ["Seleccionar..."] + CLIENTES_EXTRACTOR)
    
    with col2:
        archivos = st.file_uploader(
            "Archivos",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="extractor_files"
        )
    
    if archivos and cliente != "Seleccionar...":
        if st.button("🚀 Procesar", type="primary"):
            
            with st.spinner("Procesando..."):
                archivos_a_procesar = []
                for archivo in archivos:
                    contenido = archivo.read()
                    if archivo.name.lower().endswith('.zip'):
                        archivos_zip = extraer_archivos_zip(contenido)
                        archivos_a_procesar.extend(archivos_zip)
                    else:
                        archivos_a_procesar.append((archivo.name, contenido, archivo.type))
                
                if not archivos_a_procesar:
                    agregar_mensaje("warning", "⚠️ Sin archivos válidos")
                    return
                
                progress = st.progress(0)
                resultados = []
                
                for i, (nombre, contenido, tipo) in enumerate(archivos_a_procesar):
                    progress.progress((i + 1) / len(archivos_a_procesar))
                    
                    try:
                        datos = extraer_datos_con_vision_api(contenido, nombre, tipo)
                        
                        emisor = limpiar_nombre(datos.get("emisor", ""))
                        if not emisor:
                            emisor = datos.get("id_operacion", "") or "SIN_EMISOR"
                        
                        monto_str = str(datos.get('monto_float', 0.0)).replace('.', ',')
                        id_operacion = datos.get("id_operacion", "")
                        
                        resultados.append({
                            "emisor": emisor,
                            "monto": monto_str,
                            "id_operacion": id_operacion
                        })
                        
                        time.sleep(0.5)
                    except:
                        pass
                
                progress.empty()
                
                # Generar doble partida
                lineas_nexo = []
                lineas_cliente = []
                
                for r in resultados:
                    dp = generar_doble_partida(r["emisor"], r["monto"], r["id_operacion"], cliente)
                    lineas_nexo.append(dp["nexo"])
                    lineas_cliente.append(dp["cliente"])
                
                st.success(f"✅ {len(resultados)} procesados")
                
                col_n, col_c = st.columns(2)
                
                with col_n:
                    st.markdown("**📊 NEXO**")
                    texto_nexo = "\n".join(lineas_nexo)
                    st.text_area("", texto_nexo, height=300, key="nexo")
                    st.download_button("📥 Descargar", texto_nexo, file_name=f"nexo_{cliente}.csv")
                
                with col_c:
                    st.markdown(f"**📄 {cliente.upper()}**")
                    texto_cliente = "\n".join(lineas_cliente)
                    st.text_area("", texto_cliente, height=300, key="cliente")
                    st.download_button("📥 Descargar", texto_cliente, file_name=f"{cliente}.csv")

# =============================================================================
# MAIN
# =============================================================================

def main():
    init_db()
    cargar_css()
    
    st.title("🏦 SIDERA ERP")
    
    mostrar_mensajes()
    
    dia_formato = datetime.now().strftime("%d/%m/%Y")
    
    mostrar_semaforos(dia_formato)
    
    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏢 MOSTRADOR",
        "📥 FONDEO",
        "🔄 EXTRACTOR",
        "✅ HISTORIAL"
    ])
    
    with tab1:
        tab_mostrador(dia_formato)
    
    with tab2:
        tab_fondeo(dia_formato)
    
    with tab3:
        tab_extractor()
    
    with tab4:
        tab_historial()

if __name__ == "__main__":
    main()
