"""
SISTEMA SIDERA UNIFICADO
Versión mejorada con diseño fiel al original
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

# Inicializar session state
if 'editando_id' not in st.session_state:
    st.session_state.editando_id = None
if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []
if 'filtro_activo' not in st.session_state:
    st.session_state.filtro_activo = 'Todo'
if 'mensajes' not in st.session_state:
    st.session_state.mensajes = []

# Constantes
DB_NAME = "sidera_datos.db"
CLIENTES_FONDEO = ['Celso', 'Vertice', 'Canella', '3D Land', 'Moreira', 'Giampaoli', 'Otro']
CLIENTES_MOSTRADOR = ['Giardino', 'Fimex', 'Alcaide', 'Red Bird', 'Parra', 'Moreira', 'Giampaoli', 'Manu Camps Salta', 'CC General', 'Ajustes Manuales']
CLIENTES_EXTRACTOR = ["Celso", "Canella", "Vertice", "3D Land", "Moreira", "Giampaoli", "Otro"]

# Cargar .env
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
# CSS PERSONALIZADO - Réplica del HTML original
# =============================================================================

def cargar_css():
    st.markdown("""
    <style>
        /* Reset Streamlit defaults */
        .main {
            background-color: #f4f7f6;
            padding: 0;
        }
        
        /* Header navbar style */
        .navbar-sidera {
            background: #212529;
            color: white;
            padding: 1rem 2rem;
            margin-bottom: 1.5rem;
            border-radius: 0;
        }
        
        .navbar-sidera h1 {
            color: white;
            font-size: 1.3rem;
            margin: 0;
            font-weight: 600;
        }
        
        /* Cards estilo Bootstrap */
        .card-sidera {
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            padding: 1.5rem;
            margin-bottom: 1rem;
            border: none;
        }
        
        .card-sidera.border-success {
            border-top: 5px solid #198754 !important;
        }
        
        .card-sidera.border-danger {
            border-top: 5px solid #dc3545 !important;
        }
        
        /* Semáforos compactos */
        .kpi-diferencia {
            padding: 8px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1rem;
            display: inline-block;
        }
        
        .kpi-diferencia.verde {
            background-color: #198754;
            color: white;
        }
        
        .kpi-diferencia.rojo {
            background-color: #dc3545;
            color: white;
        }
        
        .kpi-diferencia.gris {
            background-color: #e9ecef;
            color: #6c757d;
        }
        
        /* Tabla custom */
        .tabla-mostrador {
            width: 100%;
            border-collapse: collapse;
            background: white;
        }
        
        .tabla-mostrador thead {
            background: #f8f9fa;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .tabla-mostrador th {
            padding: 12px 8px;
            font-size: 0.9rem;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
            text-align: left;
        }
        
        .tabla-mostrador td {
            padding: 12px 8px;
            border-bottom: 1px solid #dee2e6;
            vertical-align: middle;
        }
        
        .tabla-mostrador tr:hover {
            background-color: #f8f9fa;
        }
        
        .tabla-mostrador tr.pendiente {
            background-color: white;
        }
        
        .tabla-mostrador tr.sugerido {
            background-color: #fff3cd;
        }
        
        .tabla-mostrador tr.completado {
            background-color: #d1e7dd;
        }
        
        /* Badges y estados */
        .badge-sidera {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-block;
        }
        
        .badge-success {
            background-color: #198754;
            color: white;
        }
        
        .badge-warning {
            background-color: #ffc107;
            color: #000;
        }
        
        .badge-secondary {
            background-color: #6c757d;
            color: white;
        }
        
        .badge-info {
            background-color: #0dcaf0;
            color: #000;
        }
        
        .estado-punto {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
        }
        
        .punto-verde { background-color: #198754; }
        .punto-amarillo { background-color: #ffc107; }
        .punto-gris { background-color: #6c757d; }
        
        /* Botones pequeños */
        .btn-tabla {
            padding: 4px 10px;
            font-size: 0.85rem;
            border-radius: 4px;
            border: 1px solid;
            background: white;
            cursor: pointer;
            margin-right: 4px;
            display: inline-block;
            text-decoration: none;
        }
        
        .btn-tabla.success {
            border-color: #198754;
            color: #198754;
        }
        
        .btn-tabla.success:hover {
            background-color: #198754;
            color: white;
        }
        
        .btn-tabla.primary {
            border-color: #0d6efd;
            color: #0d6efd;
        }
        
        .btn-tabla.primary:hover {
            background-color: #0d6efd;
            color: white;
        }
        
        .btn-tabla.danger {
            border-color: #dc3545;
            color: #dc3545;
        }
        
        .btn-tabla.danger:hover {
            background-color: #dc3545;
            color: white;
        }
        
        /* Filtros */
        .btn-filtro {
            padding: 6px 16px;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 20px;
            border: 1px solid #dee2e6;
            background: white;
            color: #495057;
            cursor: pointer;
            margin-right: 6px;
            margin-bottom: 6px;
        }
        
        .btn-filtro.activo {
            background-color: #0d6efd;
            color: white;
            border-color: #0d6efd;
        }
        
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            background-color: transparent;
            border-bottom: 2px solid #dee2e6;
        }
        
        .stTabs [data-baseweb="tab"] {
            background-color: transparent;
            border: none;
            border-bottom: 3px solid transparent;
            font-weight: 600;
            color: #495057;
            padding: 12px 24px;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: transparent !important;
            color: #0d6efd !important;
            border-bottom-color: #0d6efd !important;
        }
        
        /* Alertas */
        .alert-sidera {
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 1rem;
            font-weight: 500;
        }
        
        .alert-success {
            background-color: #d1e7dd;
            color: #0f5132;
            border-left: 4px solid #198754;
        }
        
        .alert-warning {
            background-color: #fff3cd;
            color: #664d03;
            border-left: 4px solid #ffc107;
        }
        
        .alert-danger {
            background-color: #f8d7da;
            color: #842029;
            border-left: 4px solid #dc3545;
        }
        
        .alert-info {
            background-color: #cfe2ff;
            color: #084298;
            border-left: 4px solid #0d6efd;
        }
        
        /* Ocultar elementos de Streamlit */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display: none;}
        
        /* Botones de Streamlit */
        .stButton button {
            border-radius: 6px;
            font-weight: 600;
            padding: 8px 16px;
        }
        
        /* Inputs */
        .stTextInput input, .stSelectbox select, .stNumberInput input {
            border-radius: 6px;
            border: 1px solid #ced4da;
        }
        
        /* Contenedor scrolleable */
        .scroll-container {
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# FUNCIONES DE BD
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
# FUNCIONES DE LIMPIEZA
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
# FUNCIÓN PARA MOSTRAR MENSAJES
# =============================================================================

def mostrar_mensajes():
    if st.session_state.mensajes:
        for tipo, msg in st.session_state.mensajes:
            st.markdown(f'<div class="alert-sidera alert-{tipo}">{msg}</div>', unsafe_allow_html=True)
        st.session_state.mensajes = []

def agregar_mensaje(tipo, mensaje):
    st.session_state.mensajes.append((tipo, mensaje))

# =============================================================================
# NAVBAR
# =============================================================================

def mostrar_navbar():
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    
    st.markdown(f"""
    <div class="navbar-sidera">
        <h1>🏦 SIDERA ERP - Auditoría Diferencia Cero</h1>
    </div>
    """, unsafe_allow_html=True)

# =============================================================================
# SEMÁFOROS COMPACTOS
# =============================================================================

def mostrar_semaforos(dia_formato):
    conn = get_db_connection()
    
    # Datos de Nexo
    saldos = conn.execute("SELECT * FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
    nexo_ingresos = saldos['nexo_ingresos'] if saldos else 0
    nexo_egresos = saldos['nexo_egresos'] if saldos else 0
    
    # Datos del sistema
    sis_ingresos = conn.execute(
        "SELECT SUM(monto) FROM transacciones WHERE tipo='ENTRADA' AND fecha_pedido LIKE ?",
        (f'{dia_formato}%',)
    ).fetchone()[0] or 0
    
    sis_egresos = conn.execute(
        "SELECT SUM(monto) FROM transacciones WHERE tipo='SALIDA' AND estado='COMPLETADO' AND fecha_pedido LIKE ?",
        (f'{dia_formato}%',)
    ).fetchone()[0] or 0
    
    comision_egresos = sis_egresos * 0.0075
    total_sis_egresos = sis_egresos + comision_egresos
    
    dif_ingresos = nexo_ingresos - sis_ingresos
    dif_egresos = nexo_egresos - total_sis_egresos
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div class="card-sidera border-success">
            <h5 style="color: #198754; font-weight: bold; margin-bottom: 1rem;">📥 INGRESOS (Fondeo)</h5>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; align-items: center;">
                <div>
                    <label style="font-size: 0.85rem; color: #6c757d; font-weight: 600;">Nexo Declara:</label>
                    <h5 style="color: #198754; margin-top: 0.5rem;">${nexo_ingresos:,.0f}</h5>
                </div>
                <div style="text-align: center;">
                    <label style="font-size: 0.85rem; color: #6c757d; font-weight: 600;">Sistema Leyó:</label>
                    <h5 style="margin-top: 0.5rem;">${sis_ingresos:,.0f}</h5>
                </div>
                <div style="text-align: right;">
                    <label style="font-size: 0.85rem; color: #6c757d; font-weight: 600;">Diferencia:</label>
                    <div style="margin-top: 0.5rem;">
                        {'<span class="kpi-diferencia verde">✅ $0</span>' if abs(dif_ingresos) < 1 and sis_ingresos > 0 else 
                         '<span class="kpi-diferencia gris">$0</span>' if abs(dif_ingresos) < 1 else 
                         f'<span class="kpi-diferencia rojo">❌ ${dif_ingresos:,.0f}</span>'}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Formulario para editar Nexo Ingresos
        with st.expander("✏️ Actualizar Nexo Ingresos", expanded=False):
            new_ing = st.number_input("Monto Ingresos", value=float(nexo_ingresos), step=1000.0, key="edit_nexo_ing")
            if st.button("💾 Guardar", key="save_ing"):
                row = conn.execute("SELECT fecha FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
                if row:
                    conn.execute("UPDATE saldos_diarios SET nexo_ingresos = ? WHERE fecha = ?", (new_ing, dia_formato))
                else:
                    conn.execute("INSERT INTO saldos_diarios (fecha, nexo_ingresos, nexo_egresos) VALUES (?, ?, ?)", (dia_formato, new_ing, 0))
                conn.commit()
                agregar_mensaje("success", "✅ Nexo Ingresos actualizado")
                st.rerun()
    
    with col2:
        st.markdown(f"""
        <div class="card-sidera border-danger">
            <h5 style="color: #dc3545; font-weight: bold; margin-bottom: 1rem;">📤 EGRESOS (Giardino, Alcaide...)</h5>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; align-items: center;">
                <div>
                    <label style="font-size: 0.85rem; color: #6c757d; font-weight: 600;">Nexo Declara:</label>
                    <h5 style="color: #dc3545; margin-top: 0.5rem;">${nexo_egresos:,.0f}</h5>
                </div>
                <div style="text-align: center;">
                    <label style="font-size: 0.85rem; color: #6c757d; font-weight: 600;">Sistema Leyó:</label>
                    <div style="margin-top: 0.5rem;">
                        <div style="font-size: 0.9rem; font-weight: 600;">${sis_egresos:,.0f}</div>
                        <div style="font-size: 0.8rem; color: #6c757d;">+ 0.75%: ${comision_egresos:,.0f}</div>
                        <div style="font-size: 1rem; font-weight: bold; border-top: 2px solid #dee2e6; padding-top: 0.25rem; margin-top: 0.25rem;">${total_sis_egresos:,.0f}</div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <label style="font-size: 0.85rem; color: #6c757d; font-weight: 600;">Diferencia:</label>
                    <div style="margin-top: 0.5rem;">
                        {'<span class="kpi-diferencia verde">✅ $0</span>' if abs(dif_egresos) < 1 and total_sis_egresos > 0 else 
                         '<span class="kpi-diferencia gris">$0</span>' if abs(dif_egresos) < 1 else 
                         f'<span class="kpi-diferencia rojo">❌ ${dif_egresos:,.0f}</span>'}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Formulario para editar Nexo Egresos
        with st.expander("✏️ Actualizar Nexo Egresos", expanded=False):
            new_egr = st.number_input("Monto Egresos", value=float(nexo_egresos), step=1000.0, key="edit_nexo_egr")
            if st.button("💾 Guardar", key="save_egr"):
                row = conn.execute("SELECT fecha FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
                if row:
                    conn.execute("UPDATE saldos_diarios SET nexo_egresos = ? WHERE fecha = ?", (new_egr, dia_formato))
                else:
                    conn.execute("INSERT INTO saldos_diarios (fecha, nexo_ingresos, nexo_egresos) VALUES (?, ?, ?)", (dia_formato, 0, new_egr))
                conn.commit()
                agregar_mensaje("success", "✅ Nexo Egresos actualizado")
                st.rerun()
    
    conn.close()

# =============================================================================
# TAB 1: MOSTRADOR
# =============================================================================

def tab_mostrador(dia_formato):
    conn = get_db_connection()
    
    col_left, col_right = st.columns([1, 3])
    
    # COLUMNA IZQUIERDA: Formularios
    with col_left:
        # 1. Anotar Pedido
        st.markdown('<div class="card-sidera" style="border-top: 4px solid #0d6efd;">', unsafe_allow_html=True)
        st.markdown("**📝 1. Anotar Pedido**")
        
        with st.form("form_pedido", clear_on_submit=True):
            solicitante = st.selectbox("De qué hoja es...", [""] + CLIENTES_MOSTRADOR, key="sol")
            
            # Mostrar sub_cliente si es CC General
            sub_cliente = ""
            if solicitante == "CC General":
                sub_cliente = st.text_input("Nombre específico", key="sub")
            
            titular = st.text_input("Titular", key="tit")
            monto = st.text_input("$ Monto exacto", key="mon")
            
            if st.form_submit_button("Guardar", use_container_width=True):
                if solicitante and titular and monto:
                    try:
                        monto_float = limpiar_monto(monto)
                        estado = "COMPLETADO" if solicitante == 'Ajustes Manuales' else "PENDIENTE"
                        conn.execute(
                            "INSERT INTO transacciones (tipo, solicitante, sub_cliente, titular, monto, estado, fecha_pedido) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            ("SALIDA", solicitante, sub_cliente, titular, monto_float, estado, datetime.now().strftime("%d/%m/%Y %H:%M"))
                        )
                        conn.commit()
                        agregar_mensaje("success", "✅ Pedido guardado")
                        st.rerun()
                    except:
                        agregar_mensaje("danger", "❌ Monto inválido")
                else:
                    agregar_mensaje("warning", "⚠️ Completá todos los campos")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 2. Buscar Matches
        st.markdown('<div class="card-sidera" style="border-top: 4px solid #ffc107; margin-top: 1rem;">', unsafe_allow_html=True)
        st.markdown("**📥 2. Buscar Matches**")
        
        archivos_match = st.file_uploader(
            "Arrastrá comprobantes",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="match_files",
            label_visibility="collapsed"
        )
        
        if st.button("🚀 Disparar Búsqueda", use_container_width=True, type="primary"):
            if not archivos_match:
                agregar_mensaje("warning", "⚠️ No subiste archivos")
            else:
                with st.spinner("Analizando comprobantes..."):
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
                            agregar_mensaje("success", f"✅ {matches} match(es) encontrado(s)")
                        else:
                            agregar_mensaje("info", "ℹ️ No se encontraron matches")
                        st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # COLUMNA DERECHA: Tabla
    with col_right:
        st.markdown('<div class="card-sidera">', unsafe_allow_html=True)
        
        # Filtros y búsqueda
        col_filtros, col_buscar = st.columns([3, 1])
        
        with col_filtros:
            st.markdown("**Filtros:**")
            filtros_html = '<div style="margin-bottom: 1rem;">'
            filtros_html += '<button class="btn-filtro activo" onclick="alert(\'Filtro Todo\')">Todo</button>'
            for cliente in CLIENTES_MOSTRADOR:
                filtros_html += f'<button class="btn-filtro">{cliente}</button>'
            filtros_html += '</div>'
            # Por ahora sin funcionalidad de filtro interactivo
        
        with col_buscar:
            buscar = st.text_input("🔍 Buscar", key="buscar_mostrador", label_visibility="collapsed")
        
        # Obtener datos
        salidas = conn.execute(
            "SELECT * FROM transacciones WHERE tipo = 'SALIDA' AND (fecha_pedido LIKE ? OR estado IN ('PENDIENTE', 'SUGERIDO')) ORDER BY estado DESC, id DESC",
            (f'{dia_formato}%',)
        ).fetchall()
        
        # Tabla HTML
        if salidas:
            # Filtrar por búsqueda
            if buscar:
                salidas = [s for s in salidas if buscar.lower() in s['titular'].lower() or buscar.lower() in s['solicitante'].lower()]
            
            tabla_html = '<div class="scroll-container"><table class="tabla-mostrador"><thead><tr>'
            tabla_html += '<th>Estado</th><th>Hoja / Cliente</th><th>Titular Destino</th><th>Monto</th><th>Análisis IA</th><th>Acción</th>'
            tabla_html += '</tr></thead><tbody>'
            
            for salida in salidas:
                clase_fila = "completado" if salida['estado'] == 'COMPLETADO' else ("sugerido" if salida['estado'] == 'SUGERIDO' else "pendiente")
                
                tabla_html += f'<tr class="{clase_fila}">'
                
                # Estado
                if salida['estado'] == 'COMPLETADO':
                    tabla_html += '<td><span class="badge-sidera badge-success">CONFIRMADO</span></td>'
                elif salida['estado'] == 'SUGERIDO':
                    punto_color = "punto-verde" if salida['nivel_alerta'] == 'VERDE' else "punto-amarillo"
                    tabla_html += f'<td><span class="estado-punto {punto_color}"></span> Pre-Match</td>'
                else:
                    tabla_html += '<td><span class="estado-punto punto-gris"></span> Pendiente</td>'
                
                # Cliente
                cliente_html = f"<strong>{salida['solicitante']}</strong>"
                if salida['sub_cliente']:
                    cliente_html = f'<span class="badge-sidera badge-info">{salida["sub_cliente"]}</span><br>' + cliente_html
                tabla_html += f'<td>{cliente_html}</td>'
                
                # Titular
                tabla_html += f'<td>{salida["titular"]}</td>'
                
                # Monto
                tabla_html += f'<td style="color: #dc3545; font-weight: 600;">${salida["monto"]:,.2f}</td>'
                
                # Análisis
                tabla_html += f'<td style="font-size: 0.85rem;">{salida["datos_extraidos"] or "---"}</td>'
                
                # Botones (aquí usaré Streamlit buttons con keys únicos)
                tabla_html += f'<td id="btns_{salida["id"]}"></td>'
                tabla_html += '</tr>'
            
            tabla_html += '</tbody></table></div>'
            st.markdown(tabla_html, unsafe_allow_html=True)
            
            # Ahora renderizo los botones con Streamlit (fuera de la tabla HTML)
            for salida in salidas:
                with st.container():
                    # Usar columnas invisibles para alinear botones
                    cols = st.columns([1, 1, 1, 1, 1, 6])
                    
                    if salida['estado'] == 'PENDIENTE':
                        with cols[0]:
                            if st.button("✔️", key=f"ok_{salida['id']}", help="Marcar completado"):
                                conn.execute("UPDATE transacciones SET estado = 'COMPLETADO' WHERE id = ?", (salida['id'],))
                                conn.commit()
                                agregar_mensaje("success", "✅ Marcado como completado")
                                st.rerun()
                        with cols[1]:
                            if st.button("✏️", key=f"edit_{salida['id']}", help="Editar"):
                                st.session_state.editando_id = salida['id']
                                st.rerun()
                        with cols[2]:
                            if st.button("🗑️", key=f"del_{salida['id']}", help="Eliminar"):
                                conn.execute("DELETE FROM transacciones WHERE id = ?", (salida['id'],))
                                conn.commit()
                                agregar_mensaje("info", "🗑️ Eliminado")
                                st.rerun()
                    
                    elif salida['estado'] == 'SUGERIDO':
                        with cols[0]:
                            if st.button("✔️", key=f"ok_sug_{salida['id']}", help="Confirmar"):
                                conn.execute("UPDATE transacciones SET estado = 'COMPLETADO' WHERE id = ?", (salida['id'],))
                                conn.commit()
                                agregar_mensaje("success", "✅ Match confirmado")
                                st.rerun()
                        with cols[1]:
                            if st.button("❌", key=f"no_sug_{salida['id']}", help="Rechazar"):
                                conn.execute("UPDATE transacciones SET estado = 'PENDIENTE', nivel_alerta = NULL, datos_extraidos = NULL, id_operacion = NULL WHERE id = ?", (salida['id'],))
                                conn.commit()
                                agregar_mensaje("warning", "⏳ Vuelto a pendiente")
                                st.rerun()
                    
                    # Modal de edición
                    if st.session_state.editando_id == salida['id']:
                        st.markdown("---")
                        st.markdown(f"**✏️ Editando #{salida['id']}**")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            nuevo_cliente = st.selectbox("Cliente", CLIENTES_MOSTRADOR, index=CLIENTES_MOSTRADOR.index(salida['solicitante']) if salida['solicitante'] in CLIENTES_MOSTRADOR else 0, key=f"nc_{salida['id']}")
                        with col2:
                            nuevo_titular = st.text_input("Titular", value=salida['titular'], key=f"nt_{salida['id']}")
                        with col3:
                            nuevo_monto = st.text_input("Monto", value=str(salida['monto']), key=f"nm_{salida['id']}")
                        with col4:
                            col_save, col_cancel = st.columns(2)
                            with col_save:
                                if st.button("💾", key=f"save_edit_{salida['id']}"):
                                    try:
                                        monto_float = limpiar_monto(nuevo_monto)
                                        conn.execute("UPDATE transacciones SET solicitante = ?, titular = ?, monto = ? WHERE id = ?", (nuevo_cliente, nuevo_titular, monto_float, salida['id']))
                                        conn.commit()
                                        st.session_state.editando_id = None
                                        agregar_mensaje("success", "✅ Guardado")
                                        st.rerun()
                                    except:
                                        agregar_mensaje("danger", "❌ Error")
                            with col_cancel:
                                if st.button("❌", key=f"cancel_edit_{salida['id']}"):
                                    st.session_state.editando_id = None
                                    st.rerun()
        else:
            st.info("ℹ️ No hay transferencias pendientes para este día")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    conn.close()

# =============================================================================
# TAB 2: FONDEO
# =============================================================================

def tab_fondeo(dia_formato):
    st.markdown('<div class="card-sidera border-success" style="max-width: 600px; margin: 0 auto;">', unsafe_allow_html=True)
    st.markdown("### 📥 Fondeo Directo (Suma a Ingresos)")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        cliente_fondeo = st.selectbox("Quién envía...", [""] + CLIENTES_FONDEO, key="cliente_fondeo")
    
    with col2:
        archivos_fondeo = st.file_uploader(
            "Arrastrá ZIPs/Fotos",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="fondeo_files",
            label_visibility="collapsed"
        )
    
    if st.button("⚙️ Procesar y Sumar a Sistema", use_container_width=True, type="primary"):
        if not cliente_fondeo or not archivos_fondeo:
            agregar_mensaje("warning", "⚠️ Seleccioná cliente y subí archivos")
        else:
            conn = get_db_connection()
            
            with st.spinner("Procesando fondeos..."):
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
                        
                        # Anti-duplicados
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
                    agregar_mensaje("success", f"✅ {insertados} fondeo(s) procesado(s)")
                if duplicados > 0:
                    agregar_mensaje("warning", f"⚠️ {duplicados} duplicado(s) omitido(s)")
                
                st.rerun()
            
            conn.close()
    
    st.markdown('</div>', unsafe_allow_html=True)

# =============================================================================
# TAB 3: EXTRACTOR
# =============================================================================

def tab_extractor():
    st.markdown("### 🔄 Extractor + Doble Partida")
    
    st.info("📝 Procesa comprobantes y genera automáticamente las líneas para Hoja NEXO y Hoja del CLIENTE")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        cliente_seleccionado = st.selectbox(
            "¿De quién son estos comprobantes?",
            ["Seleccionar..."] + CLIENTES_EXTRACTOR,
            key="extractor_cliente"
        )
    
    with col2:
        archivos_extractor = st.file_uploader(
            "Selecciona archivos (imágenes, PDFs o ZIPs)",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="extractor_files"
        )
    
    if archivos_extractor and cliente_seleccionado != "Seleccionar...":
        if st.button("🚀 Procesar Comprobantes", type="primary", use_container_width=True):
            
            with st.spinner("Extrayendo y procesando archivos..."):
                archivos_a_procesar = []
                for archivo in archivos_extractor:
                    contenido = archivo.read()
                    if archivo.name.lower().endswith('.zip'):
                        archivos_zip = extraer_archivos_zip(contenido)
                        archivos_a_procesar.extend(archivos_zip)
                    else:
                        archivos_a_procesar.append((archivo.name, contenido, archivo.type))
                
                if not archivos_a_procesar:
                    agregar_mensaje("warning", "⚠️ No se encontraron archivos válidos")
                    return
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                resultados = []
                datos_completos = []
                
                for i, (nombre, contenido, tipo) in enumerate(archivos_a_procesar):
                    status_text.text(f"Procesando {i+1}/{len(archivos_a_procesar)}: {nombre}")
                    progress_bar.progress((i + 1) / len(archivos_a_procesar))
                    
                    try:
                        datos_extraidos = extraer_datos_con_vision_api(contenido, nombre, tipo)
                        
                        emisor = limpiar_nombre(datos_extraidos.get("emisor", ""))
                        if not emisor:
                            id_op = datos_extraidos.get("id_operacion", "")
                            emisor = id_op if id_op else "SIN_EMISOR"
                        
                        monto_str = str(datos_extraidos.get('monto_float', 0.0)).replace('.', ',')
                        id_operacion = datos_extraidos.get("id_operacion", "")
                        
                        resultado = {
                            "archivo": nombre,
                            "emisor": emisor,
                            "monto": monto_str,
                            "id_operacion": id_operacion,
                            "datos_raw": datos_extraidos
                        }
                        
                        resultados.append(resultado)
                        datos_completos.append(datos_extraidos)
                        
                        time.sleep(0.5)
                    except:
                        pass
                
                progress_bar.empty()
                status_text.empty()
                
                # Detectar duplicados
                ids_vistos = {}
                duplicados = []
                
                for item in datos_completos:
                    id_op = item.get("id_operacion", "")
                    if id_op and id_op.strip():
                        if id_op in ids_vistos:
                            if id_op not in duplicados:
                                duplicados.append(id_op)
                        else:
                            ids_vistos[id_op] = True
                
                # Filtrar duplicados
                resultados_sin_duplicados = []
                ids_ya_vistos = set()
                
                for resultado in resultados:
                    id_op = resultado["id_operacion"]
                    if id_op and id_op in duplicados:
                        if id_op not in ids_ya_vistos:
                            ids_ya_vistos.add(id_op)
                            resultados_sin_duplicados.append(resultado)
                    else:
                        resultados_sin_duplicados.append(resultado)
                
                if duplicados:
                    eliminados = len(resultados) - len(resultados_sin_duplicados)
                    agregar_mensaje("warning", f"⚠️ {eliminados} duplicado(s) eliminado(s)")
                
                # Generar doble partida
                lineas_nexo = []
                lineas_cliente = []
                
                for resultado in resultados_sin_duplicados:
                    doble_partida = generar_doble_partida(
                        resultado["emisor"],
                        resultado["monto"],
                        resultado["id_operacion"],
                        cliente_seleccionado
                    )
                    lineas_nexo.append(doble_partida["nexo"])
                    lineas_cliente.append(doble_partida["cliente"])
                
                # Mostrar resultados
                st.success(f"✅ {len(resultados_sin_duplicados)} comprobantes procesados")
                
                col_n, col_c = st.columns(2)
                
                with col_n:
                    st.markdown("### 📊 Hoja NEXO")
                    texto_nexo = "\n".join(lineas_nexo)
                    st.text_area("Copiar estas líneas", texto_nexo, height=300, key="nexo_output")
                    st.download_button("📥 Descargar NEXO", texto_nexo, file_name=f"nexo_{cliente_seleccionado}.csv", mime="text/csv")
                
                with col_c:
                    st.markdown(f"### 📄 Hoja {cliente_seleccionado.upper()}")
                    texto_cliente = "\n".join(lineas_cliente)
                    st.text_area("Copiar estas líneas", texto_cliente, height=300, key="cliente_output")
                    st.download_button(f"📥 Descargar {cliente_seleccionado}", texto_cliente, file_name=f"{cliente_seleccionado}.csv", mime="text/csv")

# =============================================================================
# TAB 4: AUDITORÍA
# =============================================================================

def tab_auditoria():
    st.markdown("### ✅ Auditoría General (Todos los días)")
    
    conn = get_db_connection()
    
    # Filtros y búsqueda
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        filtro_tipo = st.selectbox("Tipo", ["TODOS", "ENTRADA", "SALIDA"], key="filtro_tipo_aud")
    
    with col2:
        todos_clientes = sorted(list(set(CLIENTES_FONDEO + CLIENTES_MOSTRADOR)))
        filtro_cliente = st.selectbox("Cliente", ["TODOS"] + todos_clientes, key="filtro_cliente_aud")
    
    with col3:
        buscar_texto = st.text_input("🔍 Buscar nombre o monto...", key="buscar_aud")
    
    # Query
    query = "SELECT * FROM transacciones WHERE estado = 'COMPLETADO'"
    params = []
    
    if filtro_tipo != "TODOS":
        query += " AND tipo = ?"
        params.append(filtro_tipo)
    
    if filtro_cliente != "TODOS":
        query += " AND solicitante = ?"
        params.append(filtro_cliente)
    
    if buscar_texto:
        query += " AND (titular LIKE ? OR CAST(monto AS TEXT) LIKE ?)"
        params.append(f'%{buscar_texto}%')
        params.append(f'%{buscar_texto}%')
    
    query += " ORDER BY fecha_pedido DESC"
    
    resultados = conn.execute(query, params).fetchall()
    
    if resultados:
        # Botón de borrar seleccionados
        if st.session_state.seleccionados:
            if st.button(f"🗑️ Borrar ({len(st.session_state.seleccionados)}) seleccionados", type="primary"):
                for id_sel in st.session_state.seleccionados:
                    conn.execute("DELETE FROM transacciones WHERE id = ?", (id_sel,))
                conn.commit()
                agregar_mensaje("info", f"🗑️ {len(st.session_state.seleccionados)} registros eliminados")
                st.session_state.seleccionados = []
                st.rerun()
        
        st.markdown("---")
        
        # Tabla
        tabla_html = '<div class="scroll-container"><table class="tabla-mostrador"><thead><tr>'
        tabla_html += '<th><input type="checkbox" id="sel_todo"></th><th>Fecha</th><th>Flujo</th><th>Cliente</th><th>Titular</th><th>Monto</th><th>ID Op</th>'
        tabla_html += '</tr></thead><tbody>'
        
        for r in resultados:
            check_id = f"chk_{r['id']}"
            checked = "checked" if r['id'] in st.session_state.seleccionados else ""
            
            badge_color = "badge-danger" if r['tipo'] == 'SALIDA' else "badge-success"
            
            tabla_html += f'<tr>'
            tabla_html += f'<td><input type="checkbox" id="{check_id}" {checked}></td>'
            tabla_html += f'<td style="font-size: 0.85rem; color: #6c757d;">{r["fecha_pedido"]}</td>'
            tabla_html += f'<td><span class="badge-sidera {badge_color}">{r["tipo"]}</span></td>'
            tabla_html += f'<td><strong>{r["solicitante"]}</strong></td>'
            tabla_html += f'<td>{r["titular"]}</td>'
            tabla_html += f'<td style="font-weight: 600;">${r["monto"]:,.2f}</td>'
            tabla_html += f'<td style="font-size: 0.85rem; color: #6c757d;">{r["id_operacion"] or "N/A"}</td>'
            tabla_html += '</tr>'
        
        tabla_html += '</tbody></table></div>'
        st.markdown(tabla_html, unsafe_allow_html=True)
        
        # Checkboxes funcionales con Streamlit
        st.markdown("---")
        st.markdown("**Seleccionar registros para eliminar:**")
        
        col_checks = st.columns(5)
        for i, r in enumerate(resultados):
            with col_checks[i % 5]:
                if st.checkbox(f"{r['titular'][:20]}... (${r['monto']:,.0f})", key=f"sel_{r['id']}", value=r['id'] in st.session_state.seleccionados):
                    if r['id'] not in st.session_state.seleccionados:
                        st.session_state.seleccionados.append(r['id'])
                else:
                    if r['id'] in st.session_state.seleccionados:
                        st.session_state.seleccionados.remove(r['id'])
        
    else:
        st.info("ℹ️ No hay registros completados")
    
    conn.close()

# =============================================================================
# MAIN
# =============================================================================

def main():
    init_db()
    cargar_css()
    mostrar_navbar()
    mostrar_mensajes()
    
    # Día seleccionado
    dia_formato = datetime.now().strftime("%d/%m/%Y")
    
    # Semáforos arriba
    mostrar_semaforos(dia_formato)
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏢 MOSTRADOR (Salidas)",
        "📥 FONDEO (Entradas)",
        "🔄 EXTRACTOR",
        "✅ HISTORIAL GENERAL"
    ])
    
    with tab1:
        tab_mostrador(dia_formato)
    
    with tab2:
        tab_fondeo(dia_formato)
    
    with tab3:
        tab_extractor()
    
    with tab4:
        tab_auditoria()

if __name__ == "__main__":
    main()
