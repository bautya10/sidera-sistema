"""
SISTEMA SIDERA UNIFICADO
Versión final basada en capturas del sistema original
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

# Session State
if 'modal_abierto' not in st.session_state:
    st.session_state.modal_abierto = False
if 'editando_id' not in st.session_state:
    st.session_state.editando_id = None
if 'seleccionados' not in st.session_state:
    st.session_state.seleccionados = []
if 'mensajes' not in st.session_state:
    st.session_state.mensajes = []

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
# CSS - Basado en capturas
# =============================================================================

def cargar_css():
    st.markdown("""
    <style>
        /* General */
        .main { background-color: #f4f7f6; padding: 1rem 2rem; }
        
        /* Tabs Bootstrap-style */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0;
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
        
        /* Botones de filtro */
        .btn-filter {
            padding: 6px 16px;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 20px;
            border: 1px solid #dee2e6;
            background: white;
            margin-right: 8px;
            margin-bottom: 8px;
            cursor: pointer;
            display: inline-block;
        }
        
        .btn-filter.active {
            background-color: #0d6efd !important;
            color: white !important;
            border-color: #0d6efd !important;
        }
        
        /* Tabla simple */
        .tabla-simple {
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        
        .tabla-simple thead {
            background: #f8f9fa;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .tabla-simple th {
            padding: 12px 10px;
            font-size: 0.9rem;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
            text-align: left;
        }
        
        .tabla-simple td {
            padding: 12px 10px;
            border-bottom: 1px solid #dee2e6;
            vertical-align: middle;
            font-size: 0.95rem;
        }
        
        .tabla-simple tr:hover {
            background-color: #f8f9fa;
        }
        
        /* Estados de fila en Mostrador */
        .fila-pendiente {
            background-color: white;
        }
        
        .fila-sugerida {
            background-color: #fff3cd;
        }
        
        .fila-completada {
            background-color: #d1e7dd;
        }
        
        /* Badges */
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-block;
        }
        
        .badge-success { background-color: #198754; color: white; }
        .badge-danger { background-color: #dc3545; color: white; }
        .badge-warning { background-color: #ffc107; color: #000; }
        .badge-secondary { background-color: #6c757d; color: white; }
        
        /* Punto de estado */
        .punto-estado {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
        }
        
        .punto-gris { background-color: #6c757d; }
        .punto-verde { background-color: #198754; }
        .punto-amarillo { background-color: #ffc107; }
        
        /* Semáforos */
        .semaforo-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            margin-bottom: 1rem;
        }
        
        .semaforo-card.verde { border-top: 5px solid #198754; }
        .semaforo-card.rojo { border-top: 5px solid #dc3545; }
        
        .kpi {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1rem;
            display: inline-block;
        }
        
        .kpi.verde { background-color: #198754; color: white; }
        .kpi.rojo { background-color: #dc3545; color: white; }
        .kpi.gris { background-color: #e9ecef; color: #6c757d; }
        
        /* Modal overlay */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 9998;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-content {
            background: white;
            border-radius: 10px;
            padding: 2rem;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            z-index: 9999;
            position: relative;
        }
        
        .modal-header {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
        }
        
        .modal-close {
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #6c757d;
        }
        
        /* Alertas */
        .alerta {
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 1rem;
            font-weight: 500;
        }
        
        .alerta-success {
            background-color: #d1e7dd;
            color: #0f5132;
            border-left: 4px solid #198754;
        }
        
        .alerta-warning {
            background-color: #fff3cd;
            color: #664d03;
            border-left: 4px solid #ffc107;
        }
        
        .alerta-danger {
            background-color: #f8d7da;
            color: #842029;
            border-left: 4px solid #dc3545;
        }
        
        .alerta-info {
            background-color: #cfe2ff;
            color: #084298;
            border-left: 4px solid #0d6efd;
        }
        
        /* Ocultar elementos Streamlit */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display: none;}
        
        /* Scroll container */
        .scroll-tabla {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }
        
        /* Botones de acción en tabla */
        .btn-accion {
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid;
            background: white;
            cursor: pointer;
            font-size: 0.9rem;
            margin-right: 6px;
            display: inline-block;
            text-decoration: none;
        }
        
        .btn-success { border-color: #198754; color: #198754; }
        .btn-success:hover { background: #198754; color: white; }
        
        .btn-warning { border-color: #ffc107; color: #856404; }
        .btn-warning:hover { background: #ffc107; color: #000; }
        
        .btn-danger { border-color: #dc3545; color: #dc3545; }
        .btn-danger:hover { background: #dc3545; color: white; }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# FUNCIONES BD
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
# FUNCIONES UTILIDADES
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
            st.markdown(f'<div class="alerta alerta-{tipo}">{msg}</div>', unsafe_allow_html=True)
        st.session_state.mensajes = []

def agregar_mensaje(tipo, mensaje):
    # Evitar duplicados
    if (tipo, mensaje) not in st.session_state.mensajes:
        st.session_state.mensajes.append((tipo, mensaje))

# =============================================================================
# MODAL DE EDICIÓN
# =============================================================================

@st.dialog("✏️ Editar Registro")
def modal_editar(transaccion_id):
    conn = get_db_connection()
    trans = conn.execute("SELECT * FROM transacciones WHERE id = ?", (transaccion_id,)).fetchone()
    
    if not trans:
        st.error("Registro no encontrado")
        return
    
    # Determinar lista de clientes
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
# SEMÁFOROS
# =============================================================================

def mostrar_semaforos(dia_formato):
    conn = get_db_connection()
    
    saldos = conn.execute("SELECT * FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone()
    nexo_ingresos = saldos['nexo_ingresos'] if saldos else 0
    nexo_egresos = saldos['nexo_egresos'] if saldos else 0
    
    sis_ingresos = conn.execute(
        "SELECT SUM(monto) FROM transacciones WHERE tipo='ENTRADA' AND fecha_pedido LIKE ?",
        (f'{dia_formato}%',)
    ).fetchone()[0] or 0
    
    sis_egresos = conn.execute(
        "SELECT SUM(monto) FROM transacciones WHERE tipo='SALIDA' AND estado='COMPLETADO' AND fecha_pedido LIKE ?",
        (f'{dia_formato}%',)
    ).fetchone()[0] or 0
    
    comision = sis_egresos * 0.0075
    total_egresos = sis_egresos + comision
    
    dif_ing = nexo_ingresos - sis_ingresos
    dif_egr = nexo_egresos - total_egresos
    
    col1, col2 = st.columns(2)
    
    with col1:
        clase_kpi_ing = "verde" if abs(dif_ing) < 1 and sis_ingresos > 0 else ("gris" if abs(dif_ing) < 1 else "rojo")
        
        st.markdown(f"""
        <div class="semaforo-card verde">
            <h5 style="color: #198754; margin-bottom: 1rem;">📥 INGRESOS (Fondeo)</h5>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem;">
                <div>
                    <small style="color: #6c757d; font-weight: 600;">Declarado en Nexo:</small>
                    <h5 style="color: #198754; margin-top: 0.5rem;">${nexo_ingresos:,.0f}</h5>
                </div>
                <div style="text-align: center;">
                    <small style="color: #6c757d; font-weight: 600;">Sistema leyó:</small>
                    <h5 style="margin-top: 0.5rem;">${sis_ingresos:,.0f}</h5>
                </div>
                <div style="text-align: right;">
                    <small style="color: #6c757d; font-weight: 600;">Diferencia:</small>
                    <div style="margin-top: 0.5rem;">
                        <span class="kpi {clase_kpi_ing}">{'✅ $0' if abs(dif_ing) < 1 else f'❌ ${dif_ing:,.0f}'}</span>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("✏️ Actualizar Nexo Ingresos"):
            new_ing = st.number_input("Monto", value=float(nexo_ingresos), key="upd_ing")
            if st.button("💾 Guardar", key="save_ing"):
                if conn.execute("SELECT fecha FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone():
                    conn.execute("UPDATE saldos_diarios SET nexo_ingresos = ? WHERE fecha = ?", (new_ing, dia_formato))
                else:
                    conn.execute("INSERT INTO saldos_diarios (fecha, nexo_ingresos, nexo_egresos) VALUES (?, ?, ?)", (dia_formato, new_ing, 0))
                conn.commit()
                agregar_mensaje("success", "✅ Actualizado")
                st.rerun()
    
    with col2:
        clase_kpi_egr = "verde" if abs(dif_egr) < 1 and total_egresos > 0 else ("gris" if abs(dif_egr) < 1 else "rojo")
        
        st.markdown(f"""
        <div class="semaforo-card rojo">
            <h5 style="color: #dc3545; margin-bottom: 1rem;">📤 EGRESOS (Giardino, Alcaide...)</h5>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem;">
                <div>
                    <small style="color: #6c757d; font-weight: 600;">Declarado en Nexo:</small>
                    <h5 style="color: #dc3545; margin-top: 0.5rem;">${nexo_egresos:,.0f}</h5>
                </div>
                <div style="text-align: center;">
                    <small style="color: #6c757d; font-weight: 600;">Sistema leyó:</small>
                    <div style="margin-top: 0.5rem;">
                        <div style="font-weight: 600;">${sis_egresos:,.0f}</div>
                        <small style="color: #6c757d;">+ 0.75%: ${comision:,.0f}</small>
                        <div style="font-weight: bold; border-top: 2px solid #dee2e6; padding-top: 0.25rem; margin-top: 0.25rem;">${total_egresos:,.0f}</div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <small style="color: #6c757d; font-weight: 600;">Diferencia:</small>
                    <div style="margin-top: 0.5rem;">
                        <span class="kpi {clase_kpi_egr}">{'✅ $0' if abs(dif_egr) < 1 else f'❌ ${dif_egr:,.0f}'}</span>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("✏️ Actualizar Nexo Egresos"):
            new_egr = st.number_input("Monto", value=float(nexo_egresos), key="upd_egr")
            if st.button("💾 Guardar", key="save_egr"):
                if conn.execute("SELECT fecha FROM saldos_diarios WHERE fecha = ?", (dia_formato,)).fetchone():
                    conn.execute("UPDATE saldos_diarios SET nexo_egresos = ? WHERE fecha = ?", (new_egr, dia_formato))
                else:
                    conn.execute("INSERT INTO saldos_diarios (fecha, nexo_ingresos, nexo_egresos) VALUES (?, ?, ?)", (dia_formato, 0, new_egr))
                conn.commit()
                agregar_mensaje("success", "✅ Actualizado")
                st.rerun()
    
    conn.close()

# =============================================================================
# TAB MOSTRADOR
# =============================================================================

def tab_mostrador(dia_formato):
    conn = get_db_connection()
    
    col_left, col_right = st.columns([1, 3])
    
    with col_left:
        # FORMULARIO ANOTAR PEDIDO
        st.markdown("### 📝 1. Anotar Pedido")
        
        with st.form("form_pedido", clear_on_submit=True):
            solicitante = st.selectbox("De qué hoja es...", [""] + CLIENTES_MOSTRADOR)
            
            sub_cliente = ""
            if solicitante == "CC General":
                sub_cliente = st.text_input("Nombre específico")
            
            titular = st.text_input("Titular")
            monto_texto = st.text_input("$ Monto exacto")
            
            submitted = st.form_submit_button("Guardar", use_container_width=True, type="primary")
            
            if submitted:
                # VALIDACIÓN DE CAMPOS OBLIGATORIOS
                if not solicitante or solicitante == "":
                    agregar_mensaje("warning", "⚠️ Seleccioná un cliente")
                elif not titular or titular.strip() == "":
                    agregar_mensaje("warning", "⚠️ Completá el titular")
                elif not monto_texto or monto_texto.strip() == "":
                    agregar_mensaje("warning", "⚠️ Completá el monto")
                elif solicitante == "CC General" and (not sub_cliente or sub_cliente.strip() == ""):
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
                        agregar_mensaje("danger", "❌ Monto inválido")
        
        st.markdown("---")
        
        # BUSCAR MATCHES
        st.markdown("### 📥 2. Buscar Matches")
        
        archivos_match = st.file_uploader(
            "Arrastrá comprobantes",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="match_files"
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
    
    with col_right:
        # TABLA MOSTRADOR
        st.markdown("### Transferencias del Día")
        
        # Filtros
        filtros_html = '<div style="margin-bottom: 1rem;">'
        filtros_html += '<span class="btn-filter active">Día Completo</span>'
        for cliente in CLIENTES_MOSTRADOR:
            filtros_html += f'<span class="btn-filter">{cliente}</span>'
        filtros_html += '</div>'
        st.markdown(filtros_html, unsafe_allow_html=True)
        
        # Búsqueda
        buscar = st.text_input("🔍 Buscar titular...", key="buscar_most", label_visibility="collapsed")
        
        # Datos
        salidas = conn.execute(
            "SELECT * FROM transacciones WHERE tipo = 'SALIDA' AND (fecha_pedido LIKE ? OR estado IN ('PENDIENTE', 'SUGERIDO')) ORDER BY CASE WHEN estado = 'PENDIENTE' THEN 1 WHEN estado = 'SUGERIDO' THEN 2 ELSE 3 END, id DESC",
            (f'{dia_formato}%',)
        ).fetchall()
        
        if buscar:
            salidas = [s for s in salidas if buscar.lower() in s['titular'].lower()]
        
        if salidas:
            # Tabla HTML
            tabla_html = '<div class="scroll-tabla"><table class="tabla-simple"><thead><tr>'
            tabla_html += '<th>Estado</th><th>Hoja / Cliente</th><th>Titular Destino</th><th>Monto (Crédito)</th><th>Análisis IA</th><th>Acción</th>'
            tabla_html += '</tr></thead><tbody>'
            
            for s in salidas:
                clase = "fila-completada" if s['estado'] == 'COMPLETADO' else ("fila-sugerida" if s['estado'] == 'SUGERIDO' else "fila-pendiente")
                
                tabla_html += f'<tr class="{clase}">'
                
                # Estado
                if s['estado'] == 'COMPLETADO':
                    tabla_html += '<td><span class="badge badge-success">CONFIRMADO</span></td>'
                elif s['estado'] == 'SUGERIDO':
                    punto = "punto-verde" if s['nivel_alerta'] == 'VERDE' else "punto-amarillo"
                    tabla_html += f'<td><span class="punto-estado {punto}"></span> Pre-Match</td>'
                else:
                    tabla_html += '<td><span class="punto-estado punto-gris"></span> Pendiente</td>'
                
                # Cliente
                cliente_txt = f"<strong>{s['solicitante']}</strong>"
                if s['sub_cliente']:
                    cliente_txt = f'<span class="badge badge-warning">{s["sub_cliente"]}</span><br>' + cliente_txt
                tabla_html += f'<td>{cliente_txt}</td>'
                
                # Titular y Monto
                tabla_html += f'<td>{s["titular"]}</td>'
                tabla_html += f'<td style="color: #dc3545; font-weight: 600;">${s["monto"]:,.2f}</td>'
                
                # Análisis
                tabla_html += f'<td style="font-size: 0.85rem;">{s["datos_extraidos"] or "---"}</td>'
                
                # Placeholder para botones
                tabla_html += f'<td id="btns_{s["id"]}"></td>'
                tabla_html += '</tr>'
            
            tabla_html += '</tbody></table></div>'
            st.markdown(tabla_html, unsafe_allow_html=True)
            
            # BOTONES CON STREAMLIT
            st.markdown("---")
            for s in salidas:
                cols = st.columns([1, 1, 1, 1, 1, 10])
                
                if s['estado'] == 'PENDIENTE':
                    with cols[0]:
                        if st.button("✔️", key=f"ok_pend_{s['id']}", help="Marcar completado"):
                            conn.execute("UPDATE transacciones SET estado = 'COMPLETADO' WHERE id = ?", (s['id'],))
                            conn.commit()
                            agregar_mensaje("success", "✅ Marcado como completado")
                            st.rerun()
                    
                    with cols[1]:
                        if st.button("✏️", key=f"edit_{s['id']}", help="Editar"):
                            modal_editar(s['id'])
                    
                    with cols[2]:
                        if st.button("🗑️", key=f"del_pend_{s['id']}", help="Eliminar"):
                            conn.execute("DELETE FROM transacciones WHERE id = ?", (s['id'],))
                            conn.commit()
                            agregar_mensaje("info", "🗑️ Eliminado")
                            st.rerun()
                
                elif s['estado'] == 'SUGERIDO':
                    with cols[0]:
                        if st.button("✔️", key=f"ok_sug_{s['id']}", help="Confirmar"):
                            conn.execute("UPDATE transacciones SET estado = 'COMPLETADO' WHERE id = ?", (s['id'],))
                            conn.commit()
                            agregar_mensaje("success", "✅ Match confirmado")
                            st.rerun()
                    
                    with cols[1]:
                        if st.button("❌", key=f"no_sug_{s['id']}", help="Rechazar"):
                            conn.execute("UPDATE transacciones SET estado = 'PENDIENTE', nivel_alerta = NULL, datos_extraidos = NULL, id_operacion = NULL WHERE id = ?", (s['id'],))
                            conn.commit()
                            agregar_mensaje("warning", "⏳ Vuelto a pendiente")
                            st.rerun()
                    
                    with cols[2]:
                        if st.button("🗑️", key=f"del_sug_{s['id']}", help="Eliminar"):
                            conn.execute("DELETE FROM transacciones WHERE id = ?", (s['id'],))
                            conn.commit()
                            agregar_mensaje("info", "🗑️ Eliminado")
                            st.rerun()
                
                elif s['estado'] == 'COMPLETADO':
                    with cols[0]:
                        st.markdown("✔️ OK")
                    
                    with cols[1]:
                        if st.button("🗑️", key=f"del_comp_{s['id']}", help="Eliminar"):
                            conn.execute("DELETE FROM transacciones WHERE id = ?", (s['id'],))
                            conn.commit()
                            agregar_mensaje("info", "🗑️ Eliminado")
                            st.rerun()
        else:
            st.info("ℹ️ No hay transferencias para este día")
    
    conn.close()

# =============================================================================
# TAB FONDEO
# =============================================================================

def tab_fondeo(dia_formato):
    st.markdown('<div style="max-width: 600px; margin: 0 auto;">', unsafe_allow_html=True)
    st.markdown("### 📥 Fondeo Directo (Suma a Ingresos)")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        cliente_fondeo = st.selectbox("Quién envía...", [""] + CLIENTES_FONDEO)
    
    with col2:
        archivos_fondeo = st.file_uploader(
            "Arrastrá ZIPs/Fotos",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="fondeo_files"
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
# TAB EXTRACTOR
# =============================================================================

def tab_extractor():
    st.markdown("### 🔄 Extractor + Doble Partida")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        cliente_seleccionado = st.selectbox("¿De quién son?", ["Seleccionar..."] + CLIENTES_EXTRACTOR)
    
    with col2:
        archivos_extractor = st.file_uploader(
            "Selecciona archivos",
            type=['jpg', 'jpeg', 'png', 'pdf', 'zip'],
            accept_multiple_files=True,
            key="extractor_files"
        )
    
    if archivos_extractor and cliente_seleccionado != "Seleccionar...":
        if st.button("🚀 Procesar Comprobantes", type="primary"):
            
            with st.spinner("Procesando..."):
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
                resultados = []
                datos_completos = []
                
                for i, (nombre, contenido, tipo) in enumerate(archivos_a_procesar):
                    progress_bar.progress((i + 1) / len(archivos_a_procesar))
                    
                    try:
                        datos_extraidos = extraer_datos_con_vision_api(contenido, nombre, tipo)
                        
                        emisor = limpiar_nombre(datos_extraidos.get("emisor", ""))
                        if not emisor:
                            emisor = datos_extraidos.get("id_operacion", "") or "SIN_EMISOR"
                        
                        monto_str = str(datos_extraidos.get('monto_float', 0.0)).replace('.', ',')
                        id_operacion = datos_extraidos.get("id_operacion", "")
                        
                        resultados.append({
                            "archivo": nombre,
                            "emisor": emisor,
                            "monto": monto_str,
                            "id_operacion": id_operacion
                        })
                        
                        datos_completos.append(datos_extraidos)
                        
                        time.sleep(0.5)
                    except:
                        pass
                
                progress_bar.empty()
                
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
                resultados_finales = []
                ids_usados = set()
                
                for r in resultados:
                    id_op = r["id_operacion"]
                    if id_op and id_op in duplicados:
                        if id_op not in ids_usados:
                            ids_usados.add(id_op)
                            resultados_finales.append(r)
                    else:
                        resultados_finales.append(r)
                
                if duplicados:
                    agregar_mensaje("warning", f"⚠️ {len(resultados) - len(resultados_finales)} duplicados eliminados")
                
                # Generar doble partida
                lineas_nexo = []
                lineas_cliente = []
                
                for r in resultados_finales:
                    dp = generar_doble_partida(r["emisor"], r["monto"], r["id_operacion"], cliente_seleccionado)
                    lineas_nexo.append(dp["nexo"])
                    lineas_cliente.append(dp["cliente"])
                
                st.success(f"✅ {len(resultados_finales)} comprobantes procesados")
                
                col_n, col_c = st.columns(2)
                
                with col_n:
                    st.markdown("**📊 Hoja NEXO**")
                    texto_nexo = "\n".join(lineas_nexo)
                    st.text_area("", texto_nexo, height=300, key="nexo_out")
                    st.download_button("📥 Descargar", texto_nexo, file_name=f"nexo_{cliente_seleccionado}.csv")
                
                with col_c:
                    st.markdown(f"**📄 Hoja {cliente_seleccionado.upper()}**")
                    texto_cliente = "\n".join(lineas_cliente)
                    st.text_area("", texto_cliente, height=300, key="cliente_out")
                    st.download_button("📥 Descargar", texto_cliente, file_name=f"{cliente_seleccionado}.csv")

# =============================================================================
# TAB HISTORIAL (TABLA SIMPLE)
# =============================================================================

def tab_historial():
    conn = get_db_connection()
    
    st.markdown("### ✅ Auditoría General (Todos los días)")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filtro_tipo = st.selectbox("Tipo", ["TODOS", "ENTRADA", "SALIDA"])
    
    with col2:
        todos_clientes = sorted(list(set(CLIENTES_FONDEO + CLIENTES_MOSTRADOR)))
        filtro_cliente = st.selectbox("Cliente", ["TODOS"] + todos_clientes)
    
    with col3:
        buscar = st.text_input("🔍 Buscar nombre o monto...")
    
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
        # Checkboxes para selección múltiple
        col_sel, col_btn = st.columns([1, 3])
        
        with col_sel:
            sel_todo = st.checkbox("Seleccionar todo", key="sel_todo")
            
            if sel_todo:
                st.session_state.seleccionados = [r['id'] for r in resultados]
            elif not sel_todo and len(st.session_state.seleccionados) == len(resultados):
                st.session_state.seleccionados = []
        
        with col_btn:
            if st.session_state.seleccionados:
                if st.button(f"🗑️ Borrar ({len(st.session_state.seleccionados)}) seleccionados", type="primary"):
                    for id_sel in st.session_state.seleccionados:
                        conn.execute("DELETE FROM transacciones WHERE id = ?", (id_sel,))
                    conn.commit()
                    agregar_mensaje("info", f"🗑️ {len(st.session_state.seleccionados)} registros eliminados")
                    st.session_state.seleccionados = []
                    st.rerun()
        
        st.markdown("---")
        
        # TABLA SIMPLE
        tabla_html = '<div class="scroll-tabla"><table class="tabla-simple"><thead><tr>'
        tabla_html += '<th width="50">☑</th><th>Fecha</th><th>Flujo</th><th>Cliente</th><th>Titular</th><th>Monto</th><th>ID Op</th>'
        tabla_html += '</tr></thead><tbody>'
        
        for r in resultados:
            badge = "badge-danger" if r['tipo'] == 'SALIDA' else "badge-success"
            
            tabla_html += '<tr>'
            tabla_html += f'<td></td>'  # Placeholder para checkbox
            tabla_html += f'<td style="font-size: 0.85rem; color: #6c757d;">{r["fecha_pedido"]}</td>'
            tabla_html += f'<td><span class="badge {badge}">{r["tipo"]}</span></td>'
            tabla_html += f'<td><strong>{r["solicitante"]}</strong></td>'
            tabla_html += f'<td>{r["titular"]}</td>'
            tabla_html += f'<td style="font-weight: 600;">${r["monto"]:,.2f}</td>'
            tabla_html += f'<td style="font-size: 0.85rem; color: #6c757d;">{r["id_operacion"] or "N/A"}</td>'
            tabla_html += '</tr>'
        
        tabla_html += '</tbody></table></div>'
        st.markdown(tabla_html, unsafe_allow_html=True)
        
        # Checkboxes reales
        st.markdown("**Seleccionar registros:**")
        
        cols = st.columns(4)
        for i, r in enumerate(resultados):
            with cols[i % 4]:
                checked = r['id'] in st.session_state.seleccionados
                if st.checkbox(f"{r['titular'][:15]}... ${r['monto']:,.0f}", key=f"chk_{r['id']}", value=checked):
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
    
    # Título
    st.markdown("# 🏦 SIDERA ERP - Auditoría Diferencia Cero")
    
    # Mensajes
    mostrar_mensajes()
    
    # Día
    dia_formato = datetime.now().strftime("%d/%m/%Y")
    
    # Semáforos
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
        tab_historial()

if __name__ == "__main__":
    main()
